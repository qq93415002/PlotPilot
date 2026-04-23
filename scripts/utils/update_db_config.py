import sqlite3

conn = sqlite3.connect(r'f:\WORKSPACE\PlotPilot\data\aitext.db')
cursor = conn.cursor()

# 查看当前配置
cursor.execute('SELECT * FROM embedding_config')
print('更新前:')
for row in cursor.fetchall():
    print(row)

# 更新配置
cursor.execute("UPDATE embedding_config SET model_path='./.models/bge-small-zh-v1.5' WHERE id='default'")
conn.commit()

# 查看更新后配置
cursor.execute('SELECT * FROM embedding_config')
print('\n更新后:')
for row in cursor.fetchall():
    print(row)

conn.close()
print('\n配置已更新!')