import numpy as np
import pandas as pd

# 1. 载入你的数据 (请将 'your_data.csv' 替换为你实际的 Excel 或 CSV 文件名)
# 假设前三列分别是 X, Y, Efficiency
df = pd.read_csv('your_data.csv', names=['X', 'Y', 'Efficiency'], header=None)

# 2. 提取出所有“已知效率”的交点数据
known_points = df[df['Efficiency'].notna()]

# 提取已知点的 X 坐标和对应的效率 Z 值
known_x = known_points['X'].values
known_z = known_points['Efficiency'].values

# 3. 提取所有需要预测（补全）效率的 X 坐标
all_x = df['X'].values

# 4. 使用分段线性插值进行计算
# np.interp 会自动根据已知点的 X 和 Z，计算出任意 X 对应的 Z
completed_z = np.interp(all_x, known_x, known_z)

# 5. 将计算好的完整效率覆盖回表格中
df['Efficiency_Completed'] = completed_z

# 6. 保存结果到新的文件
df.to_csv('curve_0_completed.csv', index=False, header=['X', 'Y', 'Original_Eff', 'Completed_Eff'])

print("🎉 效率数据已成功补全！")
print(df[['X', 'Y', 'Completed_Eff']].head(15)) # 打印前15行预览