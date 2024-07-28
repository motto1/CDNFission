# 读取文件内容
with open('Fission_ip2cc.txt', 'r') as file:
    lines = file.readlines()

# 过滤出不带'CN'的IP地址
filtered_lines = [line for line in lines if not line.endswith('#CN\n')]

# 将过滤后的内容写回文件
with open('Fission_ip2cc.txt', 'w') as file:
    file.writelines(filtered_lines)
