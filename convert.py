import json
import re
import pdfplumber

def is_bold(font_name):
    if not font_name: return False
    name = font_name.lower()
    return "bold" in name or "bld" in name or "black" in name or "heavy" in name

def clean_text(text):
    text = text.replace('\u00a0', ' ')
    return re.sub(r'\s+', ' ', text).strip()

def clean_question_body(text):
    """
    Якщо в тексті є знак питання, видаляємо все, що йде ПІСЛЯ останнього знака питання.
    Це прибирає сміття, яке може бути між питанням і варіантами.
    """
    if '?' in text:
        # rpartition розбиває текст на 3 частини: (до ?, сам ?, після ?)
        parts = text.rpartition('?')
        # Повертаємо "до" + "?"
        return (parts[0] + parts[1]).strip()
    return text

def split_merged_options(line_data):
    """Розрізає злиплі варіанти (В. Текст С. Текст)"""
    text = line_data["text"]
    is_bold_flag = line_data["is_bold"]
    
    # Патерн: пробіл + Літера + (крапка або дужка)
    pattern = r'(\s+)([A-EА-Еa-e][\.\)])'
    
    # Вставляємо розділювач |BRK|
    modified_text = re.sub(pattern, r'|BRK|\2', text)
    
    if '|BRK|' not in modified_text:
        return [line_data]
    
    result_lines = []
    parts = modified_text.split('|BRK|')
    
    for part in parts:
        cleaned = part.strip()
        if cleaned:
            result_lines.append({"text": cleaned, "is_bold": is_bold_flag})
            
    return result_lines

def parse_pdf(filename):
    questions = []
    print(f"Обробляю файл: {filename}")
    
    with pdfplumber.open(filename) as pdf:
        raw_lines = []
        
        for i, page in enumerate(pdf.pages):
            width = page.width
            height = page.height
            
            try:
                # Обрізка полів 10px
                cropped = page.crop((0, 10, width, height - 10))
            except:
                cropped = page

            words = cropped.extract_words(keep_blank_chars=True, extra_attrs=["fontname"])
            if not words: continue
            
            words.sort(key=lambda w: (int(w['top']), w['x0']))
            
            line_buffer = []
            if not words: continue
            
            last_top = words[0]['top']
            has_bold = False
            
            for w in words:
                if abs(w['top'] - last_top) > 4:
                    text_str = " ".join([wb['text'] for wb in line_buffer])
                    if text_str.strip():
                        raw_lines.append({"text": text_str, "is_bold": has_bold})
                    
                    line_buffer = []
                    has_bold = False
                    last_top = w['top']
                
                line_buffer.append(w)
                if is_bold(w['fontname']):
                    has_bold = True
            
            if line_buffer:
                text_str = " ".join([wb['text'] for wb in line_buffer])
                if text_str.strip():
                    raw_lines.append({"text": text_str, "is_bold": has_bold})

    # РОЗРІЗАННЯ ВАРІАНТІВ
    processed_lines = []
    for line in raw_lines:
        processed_lines.extend(split_merged_options(line))

    current_q = None
    
    # Регулярки
    opt_pattern = re.compile(r'^\s*([A-EА-Еa-e])[\.\)]\s*(.*)', re.IGNORECASE)
    q_pattern = re.compile(r'^\s*(\d+)\.\s*(.*)')

    for line_data in processed_lines:
        text = clean_text(line_data["text"])
        is_bold_line = line_data["is_bold"]
        
        if not text: continue
        if text.isdigit() and len(text) < 4: continue

        # 1. ВАРІАНТ ВІДПОВІДІ
        match_opt = opt_pattern.match(text)
        if match_opt and current_q:
            opt_text = match_opt.group(2).strip()
            if not opt_text: opt_text = text[2:].strip() if len(text) > 2 else ""

            current_q["opts"].append(opt_text)
            if is_bold_line:
                current_q["c"] = len(current_q["opts"]) - 1
            continue

        # 2. НОВЕ ПИТАННЯ
        match_q = q_pattern.match(text)
        if match_q:
            if current_q:
                # Зберігаємо попереднє
                if current_q['opts']:
                    if current_q['c'] == -1: current_q['c'] = 0
                    # ЧИСТИМО ТЕКСТ ПИТАННЯ ПЕРЕД ЗБЕРЕЖЕННЯМ
                    current_q['q'] = clean_question_body(current_q['q'])
                    questions.append(current_q)
            
            current_q = {
                "id": int(match_q.group(1)),
                "q": match_q.group(2).strip(),
                "opts": [],
                "c": -1
            }
            continue
        
        # 3. ПРОДОВЖЕННЯ ТЕКСТУ
        if current_q:
            if current_q["opts"]:
                current_q["opts"][-1] += " " + text
            else:
                current_q["q"] += " " + text

    # Останнє питання
    if current_q and current_q['opts']:
        if current_q['c'] == -1: current_q['c'] = 0
        current_q['q'] = clean_question_body(current_q['q'])
        questions.append(current_q)

    return questions

if __name__ == "__main__":
    try:
        data = parse_pdf('base.pdf')
        print(f"Знайдено {len(data)} питань.")
        with open('questions.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Помилка: {e}")
        with open('questions.json', 'w', encoding='utf-8') as f:
            json.dump([], f)
