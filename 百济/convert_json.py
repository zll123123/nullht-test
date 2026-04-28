import json
import sys

def convert_to_valid_json(input_text: str) -> str:
    """
    将包含多余转义符的文本转换为标准JSON字符串
    :param input_text: 原始带多余转义的文本
    :return: 格式化后的标准JSON字符串
    """
    try:
        # 第一步：先解码第一层转义（处理 \\\" 这类多余转义）
        # 替换三重转义为单转义，再替换双重转义为单转义
        cleaned_text = input_text.replace('\\\\\\"', '\\"').replace('\\\\\'', '\\\'')
        cleaned_text = cleaned_text.replace('\\"', '"').replace("\\'", "'")
        
        # 第二步：尝试解析为JSON对象（验证并修复格式）
        json_data = json.loads(cleaned_text)
        
        # 第三步：格式化输出标准JSON（缩进2个空格，保证可读性）
        valid_json = json.dumps(json_data, ensure_ascii=False, indent=2)
        return valid_json
    
    except json.JSONDecodeError as e:
        print(f"JSON解析错误：{e}")
        print("\n可能的原因：原始文本不是合法的JSON片段，或转义符格式异常")
        sys.exit(1)
    except Exception as e:
        print(f"处理出错：{e}")
        sys.exit(1)

def main():
    """
    主函数：从指定TXT文件读取原始文本，转换后保存为JSON文件
    """
    # ========== 配置文件路径（修改这里的路径即可） ==========
    # 原始文本所在的TXT文件路径
    input_txt_path = "raw.txt"
    # 转换后JSON文件的保存路径
    output_json_path = "转换后的标准JSON.json"
    
    try:
        # 读取TXT文件中的原始文本
        with open(input_txt_path, "r", encoding="utf-8") as f:
            raw_text = f.read().strip()  # strip()去除首尾空白/换行
        
        if not raw_text:
            print("错误：读取的TXT文件为空，请检查文件内容！")
            sys.exit(1)
        
        # 转换为标准JSON
        valid_json = convert_to_valid_json(raw_text)
        
        # 保存转换后的JSON文件
        with open(output_json_path, "w", encoding="utf-8") as f:
            f.write(valid_json)
        
        print(f"✅ 转换成功！")
        print(f"📄 原始文件：{input_txt_path}")
        print(f"📄 输出文件：{output_json_path}")
        
        # 可选：打印前100个字符预览
        print("\n转换结果预览（前100字符）：")
        print(valid_json[:100] + "..." if len(valid_json) > 100 else valid_json)
    
    except FileNotFoundError:
        print(f"错误：找不到文件 {input_txt_path}，请检查文件路径是否正确！")
        sys.exit(1)
    except PermissionError:
        print(f"错误：没有权限读取/写入文件，请检查文件权限！")
        sys.exit(1)

if __name__ == "__main__":
    main()