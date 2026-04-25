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

#pragma once

#include <stdint.h>

#include <condition_variable>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace cuttlefish {

struct RawFrameHeader {
  uint32_t magic;
  uint32_t version;
  uint32_t display_number;
  uint32_t width;
  uint32_t height;
  uint32_t fourcc;
  uint32_t stride_bytes;
  uint32_t payload_size;
};

class RawFrameStreamer {
 public:
  explicit RawFrameStreamer(std::string socket_path);
  ~RawFrameStreamer();

  RawFrameStreamer(const RawFrameStreamer&) = delete;
  RawFrameStreamer& operator=(const RawFrameStreamer&) = delete;

  void OnFrame(uint32_t display_number, uint32_t width, uint32_t height,
               uint32_t fourcc, uint32_t stride_bytes, const uint8_t* pixels);

 private:
  struct Frame {
    RawFrameHeader header = {};
    std::vector<uint8_t> pixels;
  };

  void ServerLoop();
  void ClientLoop(int client_fd);
  bool SendAll(int fd, const void* data, size_t size);

  std::string socket_path_;
  std::thread server_thread_;
  int server_fd_ = -1;

  std::mutex mutex_;
  std::condition_variable frame_cv_;
  bool stopped_ = false;
  uint64_t generation_ = 0;
  Frame latest_frame_;
};

}  // namespace cuttlefish
