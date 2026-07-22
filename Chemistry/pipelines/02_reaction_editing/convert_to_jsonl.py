"""
Convert reaction editing dataset to standard training format.

This script converts qa_pairs.json to a standardized annotations.jsonl format
suitable for training multimodal models.

Standard format:
{
    "id": 0,
    "image": ["questions/0.png", "answers/0.png"],
    "conversations": [
        {"from": "human", "value": "<image>\n{prompt}"},
        {"from": "gpt", "value": "<image>"}
    ],
    "width": [1536, 1536],
    "height": [546, 512],
    "generation_flags": [0, 1]
}

Usage:
    python convert_to_jsonl.py --input ./dataset/qa_pairs.json \
        --questions-dir ./dataset/questions \
        --answers-dir ./dataset/answers \
        --output ./dataset/annotations.jsonl
"""

import argparse
import json
from pathlib import Path
from PIL import Image


def convert_to_standard_format(
    input_json: Path,
    questions_dir: Path,
    answers_dir: Path,
    output_jsonl: Path,
    prompt: str = None,
    default_size: int = 512
):
    """
    Convert qa_pairs.json to standard annotations.jsonl format.
    
    Args:
        input_json: Path to qa_pairs.json
        questions_dir: Path to questions image folder
        answers_dir: Path to answers image folder
        output_jsonl: Path to output annotations.jsonl
        prompt: Default prompt if not in metadata
        default_size: Default image size if cannot be read
    """
    print(f"Loading data from: {input_json}")
    with open(input_json, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    total = len(data)
    print(f"Total entries: {total}")
    
    if prompt is None:
        prompt = (
            "Please complete the chemical reaction equation by providing "
            "the main products on the right side of the arrow."
        )
    
    converted = 0
    errors = 0
    
    with open(output_jsonl, 'w', encoding='utf-8') as fout:
        for i, item in enumerate(data):
            # Get image paths
            q_img_key = 'question_image'
            a_img_key = 'answer_image'
            
            # Get question image dimensions
            q_img_path = questions_dir / Path(item[q_img_key]).name
            try:
                with Image.open(q_img_path) as img:
                    q_width, q_height = img.size
            except Exception:
                q_width, q_height = default_size, default_size
                errors += 1
            
            # Get answer image dimensions
            a_img_path = answers_dir / Path(item[a_img_key]).name
            try:
                with Image.open(a_img_path) as img:
                    a_width, a_height = img.size
            except Exception:
                a_width, a_height = default_size, default_size
                errors += 1
            
            # Get prompt (use item prompt or default)
            item_prompt = item.get('prompt', prompt)
            
            # Build standard format
            new_item = {
                "id": item["id"],
                "image": [item[q_img_key], item[a_img_key]],
                "conversations": [
                    {"from": "human", "value": f"<image>\n{item_prompt}"},
                    {"from": "gpt", "value": "<image>"}
                ],
                "width": [q_width, a_width],
                "height": [q_height, a_height],
                "generation_flags": [0, 1],
            }
            
            fout.write(json.dumps(new_item, ensure_ascii=False) + '\n')
            converted += 1
            
            if (i + 1) % 10000 == 0:
                print(f"Processed {i + 1}/{total}")
    
    print(f"\nConversion complete!")
    print(f"Successfully converted: {converted}")
    print(f"Errors: {errors}")
    print(f"Output: {output_jsonl}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert reaction editing dataset to standard format"
    )
    parser.add_argument(
        "--input", "-i",
        default="./dataset/qa_pairs.json",
        help="Input qa_pairs.json path"
    )
    parser.add_argument(
        "--questions-dir", "-q",
        default="./dataset/questions",
        help="Questions image folder"
    )
    parser.add_argument(
        "--answers-dir", "-a",
        default="./dataset/answers",
        help="Answers image folder"
    )
    parser.add_argument(
        "--output", "-o",
        default="./dataset/annotations.jsonl",
        help="Output annotations.jsonl path"
    )
    parser.add_argument(
        "--prompt", "-p",
        default=None,
        help="Default prompt text"
    )
    parser.add_argument(
        "--default-size", "-s",
        type=int,
        default=512,
        help="Default image size"
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
        input_path, questions_dir, answers_dir, output_path,
        args.prompt, args.default_size
    )


if __name__ == "__main__":
    main()
