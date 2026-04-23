import os
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

from huggingface_hub import snapshot_download

target_dir = r'f:\WORKSPACE\PlotPilot\.models\bge-small-zh-v1.5'

print("=" * 60)
print("下载 BAAI/bge-small-zh-v1.5 模型到本地")
print("=" * 60)
print(f"\n目标目录: {target_dir}")

try:
    local_dir = snapshot_download(
        repo_id='BAAI/bge-small-zh-v1.5',
        local_dir=target_dir,
        local_dir_use_symlinks=False
    )
    print(f"\n✓ 下载完成!")
    print(f"模型目录: {local_dir}")

    # 列出下载的文件
    print("\n下载的文件:")
    for f in os.listdir(local_dir):
        size = os.path.getsize(os.path.join(local_dir, f))
        print(f"  {f}: {size/1024:.1f} KB")

except Exception as e:
    print(f"\n✗ 下载失败: {e}")