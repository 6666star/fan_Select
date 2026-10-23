#pragma once

namespace fanselect {

constexpr double DEFAULT_K = 1.00;
constexpr double DEFAULT_K_N = 1.15;
constexpr double DEFAULT_ETA_T = 0.95;
constexpr double DEFAULT_ETA_MIN = 0.70;

constexpr double SCORE_W_ETA_HARD = 0.55;
constexpr double SCORE_W_ETA_EASY = 0.35;
constexpr double SCORE_W_MOTOR = 0.10;
constexpr double SCORE_ETA_REF = 0.83;

constexpr int FIT_H_DEGREE = 2;
constexpr int FIT_ETA_DEGREE = 4;
constexpr double FIT_R2_WARNING = 0.95;

constexpr int BRENTQ_SCAN_POINTS = 200;
constexpr double ROOT_XTOL = 1e-4;

constexpr int GRPC_DEFAULT_PORT = 50051;

}  // namespace fanselect

