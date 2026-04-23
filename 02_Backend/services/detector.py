import psutil
import torch
import platform
import json

def get_hardware_info():
    """
    检测宿主机的硬件配置，为模型路由提供依据
    """
    info = {
        "os": platform.system(),
        "cpu_cores": psutil.cpu_count(logical=False),
        "total_ram_gb": round(psutil.virtual_memory().total / (1024**3), 2),
        "gpu": "None",
        "vram_gb": 0,
        "cuda_available": False
    }
    
    # 检测 NVIDIA GPU
    if torch.cuda.is_available():
        info["cuda_available"] = True
        props = torch.cuda.get_device_properties(0)
        info["gpu"] = props.name
        info["vram_gb"] = round(props.total_mem / (1024**3), 2)
        
    # 检测 Apple Silicon (Mac)
    elif platform.system() == "Darwin" and platform.machine() == "arm64":
        info["gpu"] = "Apple Silicon"
        # Mac 统一内存，这里简化处理，实际可用内存约为总内存的 70%
        info["vram_gb"] = round(info["total_ram_gb"] * 0.7, 2)

    return info

if __name__ == "__main__":
    print(json.dumps(get_hardware_info(), indent=4))
