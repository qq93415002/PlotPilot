import os
import shutil

print("=" * 60)
print("下载 BAAI/bge-small-zh-v1.5 模型")
print("=" * 60)

# 设置 HuggingFace 镜像
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

from sentence_transformers import SentenceTransformer

print("\n[1] 下载模型...")
model = SentenceTransformer('BAAI/bge-small-zh-v1.5')
print("模型下载成功!")

# 目标路径
target = r'f:\WORKSPACE\PlotPilot\.models\bge-small-zh-v1.5'
os.makedirs(target, exist_ok=True)

# 查找缓存目录
username = os.getenv('USERNAME')
cache_base = rf'C:\Users\{username}\.cache\huggingface\hub'
snapshots_base = os.path.join(cache_base, 'snapshots')

print(f"\n[2] 查找缓存文件...")
print(f"缓存基础目录: {cache_base}")

# 遍历找 bge-small-zh-v1.5
src_dir = None
if os.path.exists(snapshots_base):
    for root, dirs, files in os.walk(snapshots_base):
        if 'bge-small-zh-v1.5' in root:
            src_dir = root
            break

if src_dir is None:
    # 尝试直接从模型缓存目录复制
    for root, dirs, files in os.walk(cache_base):
        if 'pytorch_model.bin' in files or 'model.safetensors' in files:
            if 'bge' in root.lower():
                src_dir = root
                break

if src_dir and os.path.exists(src_dir):
    print(f"找到模型目录: {src_dir}")

    print("\n[3] 复制文件到目标目录...")
    for item in os.listdir(src_dir):
        src = os.path.join(src_dir, item)
        dst = os.path.join(target, item)
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            print(f"  复制: {item}")

    print(f"\n✓ 模型已保存到: {target}")
else:
    print("\n警告: 未找到缓存文件，模型可能在默认位置")
    print("请检查 HuggingFace 缓存目录")

print("\n" + "=" * 60)