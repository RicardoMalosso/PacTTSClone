import os
import platform
import time

import psutil


class Resources:
    def __init__(self):
        try:
            self.process = psutil.Process()
            self.process.cpu_percent()
        except psutil.Error:
            self.process = None
        self.previous = {}
        psutil.cpu_percent()
        self.nvml = None
        try:
            import pynvml

            pynvml.nvmlInit()
            self.nvml = pynvml
        except Exception:
            pass

    def sample(self, pid=None) -> dict:
        memory = psutil.virtual_memory()
        rss = None
        cpu_seconds = None
        try:
            process = psutil.Process(pid) if pid and pid != os.getpid() else self.process
            if process is None:
                raise psutil.NoSuchProcess(os.getpid())
            rss = process.memory_info().rss
            times = process.cpu_times()
            cpu_seconds = times.user + times.system
        except (psutil.Error, OSError):
            if not pid or pid == os.getpid():
                cpu_seconds = time.process_time()
                # /proc/self remains valid in containers with remapped PID namespaces.
                if os.name == "posix":
                    try:
                        from pathlib import Path

                        rss = int(Path("/proc/self/statm").read_text().split()[1]) * os.sysconf(
                            "SC_PAGE_SIZE"
                        )
                    except (OSError, ValueError, IndexError):
                        pass
        gpus = []
        if self.nvml:
            n = self.nvml
            try:
                for index in range(n.nvmlDeviceGetCount()):
                    handle = n.nvmlDeviceGetHandleByIndex(index)
                    mem = n.nvmlDeviceGetMemoryInfo(handle)
                    try:
                        util = n.nvmlDeviceGetUtilizationRates(handle).gpu
                    except Exception:
                        util = None
                    name = n.nvmlDeviceGetName(handle)
                    gpus.append(
                        {
                            "index": index,
                            "name": name.decode() if isinstance(name, bytes) else name,
                            "used_bytes": mem.used,
                            "free_bytes": mem.free,
                            "total_bytes": mem.total,
                            "utilization_percent": util,
                        }
                    )
            except Exception:
                pass
        now = time.time()
        percent = None
        key = pid or os.getpid()
        previous = self.previous.get(key)
        if cpu_seconds is not None:
            if previous and now > previous[0]:
                percent = min(
                    100,
                    max(
                        0,
                        (cpu_seconds - previous[1])
                        / (now - previous[0])
                        / (psutil.cpu_count() or 1)
                        * 100,
                    ),
                )
            self.previous = {key: (now, cpu_seconds)}
        return {
            "timestamp": now,
            "process_cpu_percent": percent,
            "system_cpu_percent": psutil.cpu_percent(),
            "system_ram_used_bytes": memory.used,
            "system_ram_total_bytes": memory.total,
            "process_ram_bytes": rss,
            "process_cpu_seconds": cpu_seconds,
            "gpus": gpus,
        }

    def hardware(self):
        name = platform.processor() or platform.machine()
        if os.name == "nt":
            try:
                import winreg

                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
                ) as key:
                    name = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
            except OSError:
                pass
        else:
            try:
                from pathlib import Path

                for line in Path("/proc/cpuinfo").read_text().splitlines():
                    if line.startswith("model name"):
                        name = line.split(":", 1)[1].strip()
                        break
            except OSError:
                pass
        return {
            "cpu": name,
            "os": platform.platform(),
            "logical_cpus": psutil.cpu_count(),
            "ram_total_bytes": psutil.virtual_memory().total,
            "gpus": self.sample()["gpus"],
        }
