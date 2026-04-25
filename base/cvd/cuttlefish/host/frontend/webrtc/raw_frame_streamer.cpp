/*
 * Copyright (C) 2026 The Android Open Source Project
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include "cuttlefish/host/frontend/webrtc/raw_frame_streamer.h"

#include <errno.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>

#include <algorithm>

#include "absl/log/log.h"

namespace cuttlefish {
namespace {

constexpr uint32_t kRawFrameMagic = 0x46414b49;  // "IKAF", little-endian.
constexpr uint32_t kRawFrameVersion = 1;

}  // namespace

RawFrameStreamer::RawFrameStreamer(std::string socket_path)
    : socket_path_(std::move(socket_path)) {
  server_thread_ = std::thread([this]() { ServerLoop(); });
}

RawFrameStreamer::~RawFrameStreamer() {
  {
    std::lock_guard<std::mutex> lock(mutex_);
    stopped_ = true;
    frame_cv_.notify_all();
  }

  if (server_fd_ >= 0) {
    shutdown(server_fd_, SHUT_RDWR);
    close(server_fd_);
  }

  if (server_thread_.joinable()) {
    server_thread_.join();
  }

  unlink(socket_path_.c_str());
}

void RawFrameStreamer::OnFrame(uint32_t display_number, uint32_t width,
                               uint32_t height, uint32_t fourcc,
                               uint32_t stride_bytes,
                               const uint8_t* pixels) {
  if (width == 0 || height == 0 || stride_bytes == 0 || pixels == nullptr) {
    return;
  }

  const size_t payload_size = static_cast<size_t>(height) * stride_bytes;
  if (payload_size > UINT32_MAX) {
    LOG(WARNING) << "Raw frame too large for stream: " << payload_size;
    return;
  }

  Frame frame;
  frame.header = {
      .magic = kRawFrameMagic,
      .version = kRawFrameVersion,
      .display_number = display_number,
      .width = width,
      .height = height,
      .fourcc = fourcc,
      .stride_bytes = stride_bytes,
      .payload_size = static_cast<uint32_t>(payload_size),
  };
  frame.pixels.assign(pixels, pixels + payload_size);

  {
    std::lock_guard<std::mutex> lock(mutex_);
    latest_frame_ = std::move(frame);
    ++generation_;
  }
  frame_cv_.notify_all();
}

void RawFrameStreamer::ServerLoop() {
  const size_t max_path = sizeof(sockaddr_un::sun_path);
  if (socket_path_.size() >= max_path) {
    LOG(ERROR) << "Raw frame socket path is too long: " << socket_path_;
    return;
  }

  unlink(socket_path_.c_str());

  int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
  if (fd < 0) {
    PLOG(ERROR) << "Failed to create raw frame socket";
    return;
  }
  server_fd_ = fd;

  sockaddr_un addr = {};
  addr.sun_family = AF_UNIX;
  strncpy(addr.sun_path, socket_path_.c_str(), sizeof(addr.sun_path) - 1);

  if (bind(fd, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) != 0) {
    PLOG(ERROR) << "Failed to bind raw frame socket: " << socket_path_;
    close(fd);
    server_fd_ = -1;
    return;
  }

  chmod(socket_path_.c_str(), 0660);

  if (listen(fd, 1) != 0) {
    PLOG(ERROR) << "Failed to listen on raw frame socket: " << socket_path_;
    close(fd);
    server_fd_ = -1;
    return;
  }

  LOG(INFO) << "Raw frame socket listening at " << socket_path_;

  while (true) {
    int client_fd = accept4(fd, nullptr, nullptr, SOCK_CLOEXEC);
    if (client_fd < 0) {
      std::lock_guard<std::mutex> lock(mutex_);
      if (stopped_) {
        break;
      }
      if (errno == EINTR) {
        continue;
      }
      PLOG(ERROR) << "Failed to accept raw frame client";
      continue;
    }

    LOG(INFO) << "Raw frame client connected";
    ClientLoop(client_fd);
    close(client_fd);
    LOG(INFO) << "Raw frame client disconnected";
  }
}

void RawFrameStreamer::ClientLoop(int client_fd) {
  uint64_t sent_generation = 0;

  while (true) {
    Frame frame;
    {
      std::unique_lock<std::mutex> lock(mutex_);
      frame_cv_.wait(lock,
                     [&]() { return stopped_ || generation_ != sent_generation; });
      if (stopped_) {
        return;
      }
      sent_generation = generation_;
      frame = latest_frame_;
    }

    if (frame.pixels.empty()) {
      continue;
    }

    if (!SendAll(client_fd, &frame.header, sizeof(frame.header)) ||
        !SendAll(client_fd, frame.pixels.data(), frame.pixels.size())) {
      return;
    }
  }
}

bool RawFrameStreamer::SendAll(int fd, const void* data, size_t size) {
  const uint8_t* ptr = reinterpret_cast<const uint8_t*>(data);
  while (size > 0) {
    ssize_t written = send(fd, ptr, size, MSG_NOSIGNAL);
    if (written < 0) {
      if (errno == EINTR) {
        continue;
      }
      return false;
    }
    if (written == 0) {
      return false;
    }
    ptr += written;
    size -= written;
  }
  return true;
}

}  // namespace cuttlefish
