def transform_file(input_filename, output_filename):
    with open(input_filename, 'r') as infile, open(output_filename, 'w') as outfile:
        lines = infile.readlines()
        
        counter = 0
        for line in lines:
            parts = line.strip().split('\t')
            if len(parts) == 2:
                key, _ = parts
                outfile.write(f"{key}\t{counter}\n")
                counter += 1
                outfile.write(f"-{key}\t{counter}\n")
                counter += 1

if __name__ == "__main__":
    input_filename = "data/augmented/relations.txt" 
    output_filename = "data/augmented/relations_transformed.txt" 
    transform_file(input_filename, output_filename)
    print(f"Transformed file saved as {output_filename}")