"""
Convert T2I molecule dataset to standard training format.

This script converts metadata.jsonl to a standardized annotations.jsonl format.

For T2I datasets, the format is slightly different:
- Input has prompts in metadata
- Output should match standard format

Usage:
    python convert_to_jsonl.py --input ./output/metadata.jsonl \
        --answers-dir ./output/answers \
        --output ./output/annotations.jsonl
"""

import argparse
import json
from pathlib import Path
from PIL import Image


def convert_t2i_metadata(
    input_jsonl: Path,
    answers_dir: Path,
    output_jsonl: Path,
    default_size: int = 512
):
    """
    Convert T2I metadata to standard format.
    
    Args:
        input_jsonl: Path to input metadata.jsonl
        answers_dir: Path to answers image folder
        output_jsonl: Path to output annotations.jsonl
        default_size: Default image size
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
            
            # Get image path
            if 'image' in item and len(item['image']) > 0:
                img_path = Path(item['image'][0])
            else:
                img_path = Path(item.get('answer_image', f"answers/{i}.png"))
            
            # Get image dimensions
            full_img_path = answers_dir / img_path.name
            try:
                with Image.open(full_img_path) as img:
                    width, height = img.size
            except Exception:
                width, height = default_size, default_size
                errors += 1
            
            # Get prompt from conversations
            prompt = ""
            if 'conversations' in item and len(item['conversations']) > 0:
                for conv in item['conversations']:
                    if conv.get('from') == 'human':
                        prompt = conv.get('value', '')
                        break
            
            # Build standard format
            new_item = {
                "id": item.get("id", i),
                "image": [str(img_path)],
                "conversations": [
                    {"from": "human", "value": prompt},
                    {"from": "gpt", "value": "<image>"}
                ],
                "width": [width],
                "height": [height],
                "generation_flags": 1,
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
        description="Convert T2I metadata to standard format"
    )
    parser.add_argument(
        "--input", "-i",
        default="./output/metadata.jsonl",
        help="Input metadata.jsonl path"
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
        help="Default image size"
    )
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    answers_dir = Path(args.answers_dir)
    output_path = Path(args.output)
    
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    if not answers_dir.exists():
        raise FileNotFoundError(f"Answers directory not found: {answers_dir}")
    
    convert_t2i_metadata(
        input_path, answers_dir, output_path, args.default_size
    )


if __name__ == "__main__":
    main()
