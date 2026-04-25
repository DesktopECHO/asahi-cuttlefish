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
#include <fcntl.h>
#include <linux/memfd.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/un.h>
#include <unistd.h>

#include <algorithm>
#include <utility>

#include "absl/log/log.h"

namespace cuttlefish {
namespace {

constexpr uint32_t kRawFrameMagic = 0x46414b49;  // "IKAF", little-endian.
constexpr uint32_t kRawFrameVersion = 1;
constexpr uint32_t kDmabufFrameMagic = 0x44414b49;  // "IKAD", little-endian.
constexpr uint32_t kDmabufFrameVersion = 1;
constexpr uint32_t kShmInitMagic = 0x53414b49;  // "IKAS", little-endian.
constexpr uint32_t kShmNotifyMagic = 0x4e414b49;  // "IKAN", little-endian.
constexpr uint32_t kShmFrameVersion = 1;
constexpr size_t kRawBufferPoolSize = 4;

struct DmabufFrameHeader {
  uint32_t magic;
  uint32_t version;
  uint32_t display_number;
  uint32_t width;
  uint32_t height;
  uint32_t fourcc;
  uint32_t offset;
  uint32_t stride_bytes;
  uint32_t modifier_hi;
  uint32_t modifier_lo;
};

struct ShmInitHeader {
  uint32_t magic;
  uint32_t version;
  uint32_t slot_count;
  uint32_t slot_size;
};

struct ShmFrameHeader {
  uint32_t magic;
  uint32_t version;
  uint32_t display_number;
  uint32_t width;
  uint32_t height;
  uint32_t fourcc;
  uint32_t stride_bytes;
  uint32_t payload_size;
  uint32_t slot_index;
};

int MemfdCreate(const char* name) {
#ifdef SYS_memfd_create
  return syscall(SYS_memfd_create, name, MFD_CLOEXEC);
#else
  errno = ENOSYS;
  return -1;
#endif
}

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

  CloseFrameFd(latest_frame_);
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

  {
    std::lock_guard<std::mutex> lock(mutex_);
    if (suppress_next_raw_display_.has_value() &&
        *suppress_next_raw_display_ == display_number) {
      suppress_next_raw_display_.reset();
      return;
    }
  }

  std::shared_ptr<std::vector<uint8_t>> payload;
  {
    std::lock_guard<std::mutex> lock(mutex_);
    payload = AcquireRawBufferLocked(payload_size);
  }
  payload->assign(pixels, pixels + payload_size);

  Frame frame;
  frame.type = FrameType::kRaw;
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
  frame.pixels = std::move(payload);

  {
    std::lock_guard<std::mutex> lock(mutex_);
    CloseFrameFd(latest_frame_);
    latest_frame_ = std::move(frame);
    ++generation_;
  }
  frame_cv_.notify_all();
}

bool RawFrameStreamer::OnDmabufFrame(uint32_t display_number, uint32_t width,
                                     uint32_t height, uint32_t fourcc,
                                     int dmabuf_fd, uint32_t offset,
                                     uint32_t stride_bytes,
                                     uint32_t modifier_hi,
                                     uint32_t modifier_lo) {
  if (width == 0 || height == 0 || stride_bytes == 0 || dmabuf_fd < 0) {
    return false;
  }

  int duplicated_fd = fcntl(dmabuf_fd, F_DUPFD_CLOEXEC, 3);
  if (duplicated_fd < 0) {
    PLOG(WARNING) << "Failed to duplicate DMA-BUF fd";
    return false;
  }

  Frame frame;
  frame.type = FrameType::kDmabuf;
  frame.header = {
      .magic = kDmabufFrameMagic,
      .version = kDmabufFrameVersion,
      .display_number = display_number,
      .width = width,
      .height = height,
      .fourcc = fourcc,
      .stride_bytes = stride_bytes,
      .payload_size = 0,
  };
  frame.dmabuf_fd = duplicated_fd;
  frame.offset = offset;
  frame.modifier_hi = modifier_hi;
  frame.modifier_lo = modifier_lo;

  {
    std::lock_guard<std::mutex> lock(mutex_);
    CloseFrameFd(latest_frame_);
    latest_frame_ = std::move(frame);
    suppress_next_raw_display_ = display_number;
    ++generation_;
  }
  frame_cv_.notify_all();
  return true;
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
  ClientShm shm;

  while (true) {
    Frame frame;
    {
      std::unique_lock<std::mutex> lock(mutex_);
      frame_cv_.wait(lock,
                     [&]() { return stopped_ || generation_ != sent_generation; });
      if (stopped_) {
        CloseClientShm(shm);
        return;
      }
      sent_generation = generation_;
      frame = CopyLatestFrameLocked();
    }

    if (frame.type == FrameType::kNone) {
      continue;
    }

    bool ok = false;
    if (frame.type == FrameType::kRaw) {
      ok = SendRawFrame(client_fd, frame, shm);
    } else {
      ok = SendDmabufFrame(client_fd, frame);
    }
    CloseFrameFd(frame);
    if (!ok) {
      CloseClientShm(shm);
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

bool RawFrameStreamer::SendRawFrame(int fd, const Frame& frame,
                                    ClientShm& shm) {
  if (!frame.pixels || frame.pixels->empty()) {
    return false;
  }

  if (SendShmFrame(fd, frame, shm)) {
    return true;
  }

  return SendAll(fd, &frame.header, sizeof(frame.header)) &&
         SendAll(fd, frame.pixels->data(), frame.pixels->size());
}

bool RawFrameStreamer::SendShmInit(int fd, ClientShm& shm,
                                   size_t payload_size) {
  constexpr uint32_t kSlotCount = 4;
  const size_t slot_size = std::max<size_t>(payload_size, 1);
  if (slot_size > UINT32_MAX) {
    return false;
  }
  const size_t mapping_size = slot_size * kSlotCount;
  if (mapping_size / kSlotCount != slot_size) {
    return false;
  }

  int shm_fd = MemfdCreate("ika-raw-frame-slots");
  if (shm_fd < 0) {
    PLOG(WARNING) << "Failed to create raw frame shared memory";
    return false;
  }

  if (ftruncate(shm_fd, mapping_size) != 0) {
    PLOG(WARNING) << "Failed to size raw frame shared memory";
    close(shm_fd);
    return false;
  }

  void* mapping = mmap(nullptr, mapping_size, PROT_READ | PROT_WRITE,
                       MAP_SHARED, shm_fd, 0);
  if (mapping == MAP_FAILED) {
    PLOG(WARNING) << "Failed to map raw frame shared memory";
    close(shm_fd);
    return false;
  }

  ShmInitHeader header = {
      .magic = kShmInitMagic,
      .version = kShmFrameVersion,
      .slot_count = kSlotCount,
      .slot_size = static_cast<uint32_t>(slot_size),
  };

  iovec iov = {};
  iov.iov_base = &header;
  iov.iov_len = sizeof(header);

  alignas(struct cmsghdr) char control[CMSG_SPACE(sizeof(int))] = {};
  msghdr msg = {};
  msg.msg_iov = &iov;
  msg.msg_iovlen = 1;
  msg.msg_control = control;
  msg.msg_controllen = sizeof(control);

  cmsghdr* cmsg = CMSG_FIRSTHDR(&msg);
  cmsg->cmsg_level = SOL_SOCKET;
  cmsg->cmsg_type = SCM_RIGHTS;
  cmsg->cmsg_len = CMSG_LEN(sizeof(int));
  memcpy(CMSG_DATA(cmsg), &shm_fd, sizeof(int));

  bool sent = false;
  while (true) {
    ssize_t written = sendmsg(fd, &msg, MSG_NOSIGNAL);
    if (written < 0) {
      if (errno == EINTR) {
        continue;
      }
      break;
    }
    sent = static_cast<size_t>(written) == sizeof(header);
    break;
  }

  if (!sent) {
    munmap(mapping, mapping_size);
    close(shm_fd);
    return false;
  }

  CloseClientShm(shm);
  shm.fd = shm_fd;
  shm.data = reinterpret_cast<uint8_t*>(mapping);
  shm.slot_size = slot_size;
  shm.slot_count = kSlotCount;
  shm.next_slot = 0;

  LOG(INFO) << "Using shared-memory raw frame slots: " << kSlotCount << " x "
            << slot_size << " bytes";
  return true;
}

bool RawFrameStreamer::SendShmFrame(int fd, const Frame& frame,
                                    ClientShm& shm) {
  if (!frame.pixels || frame.pixels->empty()
      || frame.header.payload_size == 0) {
    return false;
  }

  const size_t payload_size = frame.pixels->size();
  if (payload_size > UINT32_MAX) {
    return false;
  }
  if (shm.fd < 0 || shm.data == nullptr || payload_size > shm.slot_size) {
    if (!SendShmInit(fd, shm, payload_size)) {
      return false;
    }
  }
  if (shm.fd < 0 || shm.data == nullptr || payload_size > shm.slot_size ||
      shm.slot_count == 0) {
    return false;
  }

  const uint32_t slot_index = shm.next_slot++ % shm.slot_count;
  uint8_t* slot = shm.data + static_cast<size_t>(slot_index) * shm.slot_size;
  memcpy(slot, frame.pixels->data(), payload_size);

  ShmFrameHeader header = {
      .magic = kShmNotifyMagic,
      .version = kShmFrameVersion,
      .display_number = frame.header.display_number,
      .width = frame.header.width,
      .height = frame.header.height,
      .fourcc = frame.header.fourcc,
      .stride_bytes = frame.header.stride_bytes,
      .payload_size = static_cast<uint32_t>(payload_size),
      .slot_index = slot_index,
  };

  return SendAll(fd, &header, sizeof(header));
}

bool RawFrameStreamer::SendDmabufFrame(int fd, const Frame& frame) {
  if (frame.dmabuf_fd < 0) {
    return false;
  }

  DmabufFrameHeader header = {
      .magic = kDmabufFrameMagic,
      .version = kDmabufFrameVersion,
      .display_number = frame.header.display_number,
      .width = frame.header.width,
      .height = frame.header.height,
      .fourcc = frame.header.fourcc,
      .offset = frame.offset,
      .stride_bytes = frame.header.stride_bytes,
      .modifier_hi = frame.modifier_hi,
      .modifier_lo = frame.modifier_lo,
  };

  iovec iov = {};
  iov.iov_base = &header;
  iov.iov_len = sizeof(header);

  alignas(struct cmsghdr) char control[CMSG_SPACE(sizeof(int))] = {};
  msghdr msg = {};
  msg.msg_iov = &iov;
  msg.msg_iovlen = 1;
  msg.msg_control = control;
  msg.msg_controllen = sizeof(control);

  cmsghdr* cmsg = CMSG_FIRSTHDR(&msg);
  cmsg->cmsg_level = SOL_SOCKET;
  cmsg->cmsg_type = SCM_RIGHTS;
  cmsg->cmsg_len = CMSG_LEN(sizeof(int));
  memcpy(CMSG_DATA(cmsg), &frame.dmabuf_fd, sizeof(int));

  while (true) {
    ssize_t written = sendmsg(fd, &msg, MSG_NOSIGNAL);
    if (written < 0) {
      if (errno == EINTR) {
        continue;
      }
      return false;
    }
    return static_cast<size_t>(written) == sizeof(header);
  }
}

void RawFrameStreamer::CloseClientShm(ClientShm& shm) const {
  if (shm.data != nullptr && shm.slot_size != 0 && shm.slot_count != 0) {
    munmap(shm.data, shm.slot_size * shm.slot_count);
  }
  if (shm.fd >= 0) {
    close(shm.fd);
  }
  shm = ClientShm{};
}

RawFrameStreamer::Frame RawFrameStreamer::CopyLatestFrameLocked() const {
  Frame frame;
  frame.type = latest_frame_.type;
  frame.header = latest_frame_.header;
  frame.pixels = latest_frame_.pixels;
  frame.offset = latest_frame_.offset;
  frame.modifier_hi = latest_frame_.modifier_hi;
  frame.modifier_lo = latest_frame_.modifier_lo;
  if (latest_frame_.dmabuf_fd >= 0) {
    frame.dmabuf_fd = fcntl(latest_frame_.dmabuf_fd, F_DUPFD_CLOEXEC, 3);
  }
  return frame;
}

void RawFrameStreamer::CloseFrameFd(Frame& frame) const {
  if (frame.dmabuf_fd >= 0) {
    close(frame.dmabuf_fd);
    frame.dmabuf_fd = -1;
  }
}

std::shared_ptr<std::vector<uint8_t>> RawFrameStreamer::AcquireRawBufferLocked(
    size_t size) {
  for (size_t i = 0; i < raw_buffers_.size(); ++i) {
    const size_t index = (next_raw_buffer_ + i) % raw_buffers_.size();
    auto& buffer = raw_buffers_[index];
    if (buffer.use_count() == 1) {
      next_raw_buffer_ = (index + 1) % raw_buffers_.size();
      if (buffer->capacity() < size) {
        buffer->reserve(size);
      }
      return buffer;
    }
  }

  if (raw_buffers_.size() < kRawBufferPoolSize) {
    auto buffer = std::make_shared<std::vector<uint8_t>>();
    buffer->reserve(size);
    raw_buffers_.push_back(buffer);
    next_raw_buffer_ = raw_buffers_.size() % kRawBufferPoolSize;
    return buffer;
  }

  auto buffer = std::make_shared<std::vector<uint8_t>>();
  buffer->reserve(size);
  return buffer;
}

}  // namespace cuttlefish
