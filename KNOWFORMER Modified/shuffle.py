import random

def shuffle_file_lines(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    random.shuffle(lines)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.writelines(lines)

input_filename = "data/augmented/train.txt"
output_filename = "data/augmented/train_shuffled.txt"
shuffle_file_lines(input_filename, output_filename)
input_filename = "data/augmented/valid.txt"
output_filename = "data/augmented/valid_shuffled.txt"
shuffle_file_lines(input_filename, output_filename)