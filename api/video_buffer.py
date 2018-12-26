import json
import time
import subprocess
import numpy as np
from threading import Timer, Thread
from queue import Queue

class VideoBuffer(object):
    """
    Buffer a stream using ffmpeg.
    """
    def __init__(self, buffer_seconds):
        self.buffer_seconds = buffer_seconds
        self.running = False

    def start(self, stream, fps):
        self.running = True
        self._fps = fps
        self._last_frame = None
        self._buffer = Queue(self._fps * self.buffer_seconds)
        self._create_pipe(stream)

    def _create_pipe(self, stream):
        probe_pipe = subprocess.Popen([
            "ffprobe", stream.url,
                       "-v", "error",
                       "-show_entries", "stream=width,height",
                       "-of", "json"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE)
        video_info = probe_pipe.stdout.read().decode("utf8")
        video_info = json.loads(video_info)["streams"]
        video_info = next(
            data for data in video_info
            if len(data.keys()) > 0
        )
        probe_pipe.terminate()

        self._byte_length = video_info["width"]
        self._byte_width  = video_info["height"]

        self._pipe = subprocess.Popen([
            "ffmpeg", "-i", stream.url,
                      "-loglevel", "quiet", # no text output
                      "-an", # disable audio
                      "-f", "image2pipe",
                      "-pix_fmt", "bgr24",
                      "-r", str(self._fps),
                      "-vcodec", "rawvideo", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE)

        self._thread = Thread(target=self._read_forever)
        self._thread.daemon = True
        self._thread.start()
        time.sleep(self.buffer_seconds / 2)
        self._update_last_frame()

    def stop(self):
        if self.running:
            self._pipe.terminate()
            self.running = False

    def _update_last_frame(self):
        if self.running:
            self._last_frame = self._buffer.get()

            self._timer = Timer(1.0/self._fps,
                                self._update_last_frame)
            self._timer.daemon = True
            self._timer.start()

    def _read_forever(self):
        while self.running:
            raw_image = self._pipe.stdout.read(
                self._byte_length * self._byte_width * 3)
            if len(raw_image) == 0:
                self.running = False
                return

            frame = np.fromstring(raw_image, dtype="uint8")\
                .reshape((self._byte_width, self._byte_length, 3))
            self._buffer.put(frame)

    def read(self):
        return self._last_frame
