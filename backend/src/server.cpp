#include "config.hpp"
#include "converters.hpp"
#include "engine.hpp"
#include "selector.hpp"

#include "fan_selector.grpc.pb.h"

#include <grpcpp/grpcpp.h>

#include <exception>
#include <iostream>
#include <memory>
#include <string>

namespace {

class FanSelectorServiceImpl final : public fanSelector::FanSelectorService::Service {
public:
    grpc::Status SelectFan(
        grpc::ServerContext* context,
        const fanSelector::FanSelectionRequest* request,
        fanSelector::FanSelectionResponse* response
    ) override {
        (void)context;

        if (request->airfloweasy() <= 0.0 || request->airflowhard() <= 0.0) {
            return grpc::Status(grpc::StatusCode::INVALID_ARGUMENT, "airFlowEasy and airFlowHard must be positive");
        }
        if (request->pressureeasy() <= 0.0 || request->pressurehard() <= 0.0) {
            return grpc::Status(grpc::StatusCode::INVALID_ARGUMENT, "pressureEasy and pressureHard must be positive");
        }

        const double k = request->reservecoeff() > 0.0 ? request->reservecoeff() : fanselect::DEFAULT_K;
        const double kN = request->powermargincoeff() > 0.0 ? request->powermargincoeff() : fanselect::DEFAULT_K_N;
        const double etaT = request->transefficiency() > 0.0 ? request->transefficiency() : fanselect::DEFAULT_ETA_T;
        const double etaMin = request->minefficiency() > 0.0 ? request->minefficiency() : fanselect::DEFAULT_ETA_MIN;

        try {
            fanselect::DualPeriodParams params;
            params.q1Easy = request->airfloweasy();
            params.hFEasy = request->pressureeasy();
            params.q1Hard = request->airflowhard();
            params.hFHard = request->pressurehard();

            const auto dual = fanselect::runDual(params, fanselect::SelectionCoeffs{k});
            const auto result = fanselect::runSelector(dual, etaMin, etaT, kN);
            *response = fanselect::buildSelectionResponse(dual, result);
            response->set_code(200);
            response->set_msg("success");
            return grpc::Status::OK;
        } catch (const std::exception& e) {
            response->set_code(500);
            response->set_msg(e.what());
            return grpc::Status(grpc::StatusCode::INTERNAL, e.what());
        }
    }
};

void runServer(const std::string& address) {
    FanSelectorServiceImpl service;

    grpc::ServerBuilder builder;
    builder.AddListeningPort(address, grpc::InsecureServerCredentials());
    builder.RegisterService(&service);

    std::unique_ptr<grpc::Server> server(builder.BuildAndStart());
    std::cout << "[V4 C++ gRPC] listening on " << address << std::endl;
    server->Wait();
}

}  // namespace

int main(int argc, char** argv) {
    int port = fanselect::GRPC_DEFAULT_PORT;
    if (argc >= 2) {
        port = std::stoi(argv[1]);
    }

    runServer("0.0.0.0:" + std::to_string(port));
    return 0;
}
