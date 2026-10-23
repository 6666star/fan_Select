#include "fan_db.hpp"

#include "config.hpp"

#include <sqlite3.h>

#include <algorithm>
#include <cstdlib>
#include <cmath>
#include <memory>
#include <numeric>
#include <stdexcept>
#include <string>
#include <tuple>

namespace fanselect {

double FanModel::hMin() const {
    return std::min_element(
        curvePoints.begin(),
        curvePoints.end(),
        [](const FanCurvePoint& a, const FanCurvePoint& b) { return a.h < b.h; }
    )->h;
}

double FanModel::hMax() const {
    return std::max_element(
        curvePoints.begin(),
        curvePoints.end(),
        [](const FanCurvePoint& a, const FanCurvePoint& b) { return a.h < b.h; }
    )->h;
}

double Polynomial::operator()(double x) const {
    double y = 0.0;
    for (double c : coeffs) {
        y = y * x + c;
    }
    return y;
}

namespace {

struct SqliteDbDeleter {
    void operator()(sqlite3* db) const {
        if (db != nullptr) {
            sqlite3_close(db);
        }
    }
};

using SqliteDb = std::unique_ptr<sqlite3, SqliteDbDeleter>;

class Statement {
public:
    Statement(sqlite3* db, const char* sql) {
        const int rc = sqlite3_prepare_v2(db, sql, -1, &stmt_, nullptr);
        if (rc != SQLITE_OK) {
            throw std::runtime_error(std::string("failed to prepare SQL: ") + sqlite3_errmsg(db));
        }
    }

    ~Statement() {
        if (stmt_ != nullptr) {
            sqlite3_finalize(stmt_);
        }
    }

    Statement(const Statement&) = delete;
    Statement& operator=(const Statement&) = delete;

    sqlite3_stmt* get() const { return stmt_; }

private:
    sqlite3_stmt* stmt_ = nullptr;
};

std::string sqlite_error(sqlite3* db, const std::string& prefix) {
    return prefix + ": " + (db != nullptr ? sqlite3_errmsg(db) : "unknown sqlite error");
}

std::string fan_db_path() {
    const char* env_path = std::getenv("FAN_DB_PATH");
    if (env_path != nullptr && env_path[0] != '\0') {
        return env_path;
    }
    return "data/fans.db";
}

SqliteDb open_fan_db(const std::string& path) {
    sqlite3* raw = nullptr;
    const int rc = sqlite3_open_v2(path.c_str(), &raw, SQLITE_OPEN_READONLY, nullptr);
    SqliteDb db(raw);
    if (rc != SQLITE_OK) {
        throw std::runtime_error(sqlite_error(raw, "failed to open fan database '" + path + "'"));
    }
    return db;
}

std::string column_text(sqlite3_stmt* stmt, int column) {
    const unsigned char* text = sqlite3_column_text(stmt, column);
    return text != nullptr ? reinterpret_cast<const char*>(text) : "";
}

std::vector<double> solve_linear_system(
    std::vector<std::vector<double>> A,
    std::vector<double> b
) {
    const int n = static_cast<int>(b.size());

    for (int i = 0; i < n; ++i) {
        int pivot = i;
        for (int r = i + 1; r < n; ++r) {
            if (std::abs(A[r][i]) > std::abs(A[pivot][i])) {
                pivot = r;
            }
        }

        if (std::abs(A[pivot][i]) < 1e-12) {
            throw std::runtime_error("singular matrix during polynomial fit");
        }

        if (pivot != i) {
            std::swap(A[pivot], A[i]);
            std::swap(b[pivot], b[i]);
        }

        const double div = A[i][i];
        for (int c = i; c < n; ++c) {
            A[i][c] /= div;
        }
        b[i] /= div;

        for (int r = 0; r < n; ++r) {
            if (r == i) {
                continue;
            }
            const double factor = A[r][i];
            for (int c = i; c < n; ++c) {
                A[r][c] -= factor * A[i][c];
            }
            b[r] -= factor * b[i];
        }
    }

    return b;
}

Polynomial polyfit(const std::vector<double>& x, const std::vector<double>& y, int degree) {
    const int n = degree + 1;
    std::vector<std::vector<double>> A(n, std::vector<double>(n, 0.0));
    std::vector<double> b(n, 0.0);

    for (size_t row = 0; row < x.size(); ++row) {
        std::vector<double> powers(2 * degree + 1, 1.0);
        for (int p = 1; p <= 2 * degree; ++p) {
            powers[p] = powers[p - 1] * x[row];
        }

        for (int i = 0; i < n; ++i) {
            for (int j = 0; j < n; ++j) {
                A[i][j] += powers[i + j];
            }
            b[i] += y[row] * powers[i];
        }
    }

    auto ascending = solve_linear_system(A, b);
    std::reverse(ascending.begin(), ascending.end());
    return Polynomial{ascending};
}

double r_squared(const std::vector<double>& y_true, const Polynomial& poly, const std::vector<double>& x) {
    const double mean = std::accumulate(y_true.begin(), y_true.end(), 0.0) /
        static_cast<double>(y_true.size());
    double ss_res = 0.0;
    double ss_tot = 0.0;

    for (size_t i = 0; i < y_true.size(); ++i) {
        const double pred = poly(x[i]);
        ss_res += (y_true[i] - pred) * (y_true[i] - pred);
        ss_tot += (y_true[i] - mean) * (y_true[i] - mean);
    }
    return ss_tot > 0.0 ? 1.0 - ss_res / ss_tot : 0.0;
}

std::vector<std::tuple<double, double, double>> load_curve_points(
    sqlite3* db,
    sqlite3_int64 fan_id,
    const std::string& model_id
) {
    Statement stmt(
        db,
        "SELECT q_m3_min, h_pa, eta_percent "
        "FROM fan_curve_points "
        "WHERE fan_id = ? "
        "ORDER BY point_order, id"
    );

    if (sqlite3_bind_int64(stmt.get(), 1, fan_id) != SQLITE_OK) {
        throw std::runtime_error(sqlite_error(db, "failed to bind fan_id for " + model_id));
    }

    std::vector<std::tuple<double, double, double>> points;
    while (true) {
        const int rc = sqlite3_step(stmt.get());
        if (rc == SQLITE_DONE) {
            break;
        }
        if (rc != SQLITE_ROW) {
            throw std::runtime_error(sqlite_error(db, "failed to load curve points for " + model_id));
        }

        points.emplace_back(
            sqlite3_column_double(stmt.get(), 0),
            sqlite3_column_double(stmt.get(), 1),
            sqlite3_column_double(stmt.get(), 2)
        );
    }

    return points;
}

std::vector<FanModel> loadFansFromSqlite(const std::string& path) {
    SqliteDb db = open_fan_db(path);
    Statement stmt(
        db.get(),
        "SELECT id, model_id, series, fan_type, rated_rpm, "
        "rpm_min, rpm_max, motor_kw, motor_count, "
        "COALESCE(blade_angle_deg, 0), COALESCE(withdrawable_rail_width_mm, 0), "
        "COALESCE(image_path, ''), COALESCE(manufacturer, ''), "
        "COALESCE(product_name, ''), COALESCE(product_spec, ''), "
        "COALESCE(motor_model, ''), COALESCE(factory_no, '') "
        "FROM fans "
        "WHERE enabled != 0 "
        "ORDER BY id"
    );

    std::vector<FanModel> fans;
    while (true) {
        const int rc = sqlite3_step(stmt.get());
        if (rc == SQLITE_DONE) {
            break;
        }
        if (rc != SQLITE_ROW) {
            throw std::runtime_error(sqlite_error(db.get(), "failed to load fans"));
        }

        const sqlite3_int64 fan_id = sqlite3_column_int64(stmt.get(), 0);
        const std::string model_id = column_text(stmt.get(), 1);
        const std::string series = column_text(stmt.get(), 2);
        const std::string fan_type = column_text(stmt.get(), 3);
        const double rated_rpm = sqlite3_column_double(stmt.get(), 4);
        const double rpm_min = sqlite3_column_double(stmt.get(), 5);
        const double rpm_max = sqlite3_column_double(stmt.get(), 6);
        const double motor_kw = sqlite3_column_double(stmt.get(), 7);
        const int motor_count = sqlite3_column_int(stmt.get(), 8);
        const double bladeAngleDeg = sqlite3_column_double(stmt.get(), 9);
        const double railWidthMm = sqlite3_column_double(stmt.get(), 10);
        const std::string imagePath = column_text(stmt.get(), 11);
        const std::string manufacturer = column_text(stmt.get(), 12);
        const std::string productName = column_text(stmt.get(), 13);
        const std::string productSpec = column_text(stmt.get(), 14);
        const std::string motorModel = column_text(stmt.get(), 15);
        const std::string factoryNo = column_text(stmt.get(), 16);

        if (model_id.empty()) {
            throw std::runtime_error("fan database contains a row with empty model_id");
        }
        if (rated_rpm <= 0.0 || rpm_min <= 0.0 || rpm_max <= 0.0 || rpm_min > rpm_max) {
            throw std::runtime_error("fan '" + model_id + "' has invalid rpm settings");
        }
        if (motor_kw <= 0.0 || motor_count <= 0) {
            throw std::runtime_error("fan '" + model_id + "' has invalid motor settings");
        }

        auto raw_points = load_curve_points(db.get(), fan_id, model_id);
        FanModel fan = makeFanFromData(
            model_id,
            series,
            rated_rpm,
            {rpm_min, rpm_max},
            motor_kw,
            motor_count,
            raw_points,
            fan_type.empty() ? "counter_rotating" : fan_type
        );
        fan.bladeAngleDeg = bladeAngleDeg;
        fan.railWidthMm = railWidthMm;
        fan.imagePath = imagePath;
        fan.manufacturer = manufacturer;
        fan.productName = productName;
        fan.productSpec = productSpec;
        fan.motorModel = motorModel;
        fan.factoryNo = factoryNo;
        fans.push_back(std::move(fan));
    }

    if (fans.empty()) {
        throw std::runtime_error("fan database '" + path + "' has no enabled fans");
    }

    return fans;
}

}  // namespace

FanModel makeFanFromData(
    const std::string& model_id,
    const std::string& series,
    double rpm,
    std::pair<double, double> rpm_range,
    double motor_kw,
    int motor_count,
    const std::vector<std::tuple<double, double, double>>& raw_data,
    const std::string& fan_type
) {
    if (raw_data.size() < 5) {
        throw std::invalid_argument("fan '" + model_id + "' requires at least five curve points");
    }

    auto sorted = raw_data;
    std::sort(sorted.begin(), sorted.end(), [](const auto& a, const auto& b) {
        return std::get<0>(a) < std::get<0>(b);
    });

    std::vector<FanCurvePoint> points;
    points.reserve(sorted.size());
    for (const auto& [q_min, h, eta_pct] : sorted) {
        if (q_min <= 0.0 || h <= 0.0 || eta_pct <= 0.0) {
            throw std::invalid_argument("fan '" + model_id + "' contains invalid curve point data");
        }
        points.push_back(FanCurvePoint{q_min / 60.0, h, eta_pct / 100.0});
    }

    return FanModel{
        model_id,
        series,
        fan_type,
        rpm,
        rpm_range,
        motor_kw,
        motor_count,
        points,
    };
}

FanInterpolated buildFanInterpolated(const FanModel& fan, int H_deg, int eta_deg) {
    std::vector<double> Q;
    std::vector<double> H;
    std::vector<double> eta;
    Q.reserve(fan.curvePoints.size());
    H.reserve(fan.curvePoints.size());
    eta.reserve(fan.curvePoints.size());
                       
    
    for (const auto& point : fan.curvePoints) {
        Q.push_back(point.q);
        H.push_back(point.h);
        eta.push_back(point.eta);
    }

    Polynomial H_poly = polyfit(Q, H, H_deg);
    Polynomial eta_poly = polyfit(Q, eta, eta_deg);

    return FanInterpolated{
        fan,
        H_poly,
        eta_poly,
        Q.front(),
        Q.back(),
        r_squared(H, H_poly, Q),
        r_squared(eta, eta_poly, Q),
    };
}

const std::vector<FanModel>& fanDb() {
    static const std::vector<FanModel> db = loadFansFromSqlite(fan_db_path());
    return db;
}

}  // namespace fanselect
