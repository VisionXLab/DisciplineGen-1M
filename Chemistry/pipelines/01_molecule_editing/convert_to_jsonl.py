"""
Convert molecule editing metadata to standard training format.

This script converts the internal metadata.jsonl to a standardized format
suitable for training multimodal models.

Standard format:
{
    "id": 0,
    "image": ["questions/0.png", "answers/0.png"],
    "conversations": [
        {"from": "human", "value": "<image>\n{instruction}"},
        {"from": "gpt", "value": "<image>"}
    ],
    "width": [512, 512],
    "height": [512, 512],
    "generation_flags": [0, 1]
}

Usage:
    python convert_to_jsonl.py --input ./output/metadata.jsonl \
        --questions-dir ./output/questions \
        --answers-dir ./output/answers \
        --output ./output/annotations.jsonl
"""

import argparse
import json
from pathlib import Path
from PIL import Image


def convert_to_standard_format(
    input_jsonl: Path,
    questions_dir: Path,
    answers_dir: Path,
    output_jsonl: Path,
    default_size: int = 512
):
    """
    Convert metadata to standard training format.
    
    Args:
        input_jsonl: Path to input metadata.jsonl
        questions_dir: Path to questions image folder
        answers_dir: Path to answers image folder
        output_jsonl: Path to output annotations.jsonl
        default_size: Default image size if cannot be read
    """
    total_lines = sum(1 for _ in open(input_jsonl, 'r', encoding='utf-8'))
    print(f"Total entries: {total_lines}")
    
    converted = 0
    errors = 0
    
    with open(input_jsonl, 'r', encoding='utf-8') as fin, \
         open(output_jsonl, 'w', encoding='utf-8') as fout:
        
        for i, line in enumerate(fin):
            if not line.strip():
                continue
            
            item = json.loads(line)
            
            # Get question image dimensions
            q_img_path = questions_dir / Path(item['question_image']).name
            try:
                with Image.open(q_img_path) as img:
                    q_width, q_height = img.size
            except Exception:
                q_width, q_height = default_size, default_size
                errors += 1
            
            # Get answer image dimensions
            a_img_path = answers_dir / Path(item['answer_image']).name
            try:
                with Image.open(a_img_path) as img:
                    a_width, a_height = img.size
            except Exception:
                a_width, a_height = default_size, default_size
                errors += 1
            
            # Build standard format
            new_item = {
                "id": item["id"],
                "image": [item["question_image"], item["answer_image"]],
                "conversations": [
                    {"from": "human", "value": f"<image>\n{item['instruction']}"},
                    {"from": "gpt", "value": "<image>"}
                ],
                "width": [q_width, a_width],
                "height": [q_height, a_height],
                "generation_flags": [0, 1],
            }
            
            fout.write(json.dumps(new_item, ensure_ascii=False) + '\n')
            converted += 1
            
            if (i + 1) % 5000 == 0:
                print(f"Processed {i + 1}/{total_lines}")
    
    print(f"\nConversion complete!")
    print(f"Successfully converted: {converted}")
    print(f"Errors: {errors}")
    print(f"Output: {output_jsonl}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert molecule editing metadata to standard format"
    )
    parser.add_argument(
        "--input", "-i",
        default="./output/metadata.jsonl",
        help="Input metadata.jsonl path"
    )
    parser.add_argument(
        "--questions-dir", "-q",
        default="./output/questions",
        help="Questions image folder"
    )
    parser.add_argument(
        "--answers-dir", "-a",
        default="./output/answers",
        help="Answers image folder"
    )
    parser.add_argument(
        "--output", "-o",
        default="./output/annotations.jsonl",
        help="Output annotations.jsonl path"
    )
    parser.add_argument(
        "--default-size", "-s",
        type=int,
        default=512,
        help="Default image size if cannot be read"
    )
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    questions_dir = Path(args.questions_dir)
    answers_dir = Path(args.answers_dir)
    output_path = Path(args.output)
    
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    if not questions_dir.exists():
        raise FileNotFoundError(f"Questions directory not found: {questions_dir}")
    if not answers_dir.exists():
        raise FileNotFoundError(f"Answers directory not found: {answers_dir}")
    
    convert_to_standard_format(
        input_path, questions_dir, answers_dir, output_path, args.default_size
    )


if __name__ == "__main__":
    main()
