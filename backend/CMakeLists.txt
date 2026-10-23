cmake_minimum_required(VERSION 3.20)

project(fan_selector_backend LANGUAGES CXX)

# Export the exact compiler flags and include paths for IDE IntelliSense.
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(THREADS_PREFER_PTHREAD_FLAG ON)
set(CMAKE_THREAD_LIBS_INIT "-lpthread")
set(CMAKE_HAVE_LIBC_PTHREAD 1)
set(CMAKE_USE_PTHREADS_INIT 1)
find_package(Threads REQUIRED)

find_package(Protobuf REQUIRED)
find_package(gRPC CONFIG REQUIRED)
find_package(SQLite3 REQUIRED)

set(PROTO_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../proto)
set(PROTO_FILE ${PROTO_DIR}/fan_selector.proto)
set(GENERATED_DIR ${CMAKE_CURRENT_BINARY_DIR}/generated)
file(MAKE_DIRECTORY ${GENERATED_DIR})

find_program(PROTOC protoc HINTS C:/msys64/mingw64/bin)
find_program(GRPC_CPP_PLUGIN grpc_cpp_plugin HINTS C:/msys64/mingw64/bin)

add_custom_command(
    OUTPUT
        ${GENERATED_DIR}/fan_selector.pb.cc
        ${GENERATED_DIR}/fan_selector.pb.h
        ${GENERATED_DIR}/fan_selector.grpc.pb.cc
        ${GENERATED_DIR}/fan_selector.grpc.pb.h
    COMMAND ${PROTOC}
    ARGS
        --proto_path=${PROTO_DIR}
        --cpp_out=${GENERATED_DIR}
        --grpc_out=${GENERATED_DIR}
        --plugin=protoc-gen-grpc=${GRPC_CPP_PLUGIN}
        ${PROTO_FILE}
    DEPENDS ${PROTO_FILE}
)

add_library(fan_selection_core
    src/engine.cpp
    src/fan_db.cpp
    src/selector.cpp
)
target_include_directories(fan_selection_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_link_libraries(fan_selection_core PUBLIC SQLite::SQLite3)

add_executable(fan_selector_server
    src/server.cpp
    src/converters.cpp
    ${GENERATED_DIR}/fan_selector.pb.cc
    ${GENERATED_DIR}/fan_selector.grpc.pb.cc
)
target_include_directories(fan_selector_server PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${GENERATED_DIR}
)
target_link_libraries(fan_selector_server PRIVATE
    fan_selection_core
    gRPC::grpc++
    protobuf::libprotobuf
    Threads::Threads
)
