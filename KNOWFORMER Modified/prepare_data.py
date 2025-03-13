import json
import os
import random
from collections import defaultdict

def load_json_data(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data

def create_entity_mappings(data):
    entities = set()
    for node in data['nodes']:
        entities.add(node['id'])
    entity2id = {entity: idx for idx, entity in enumerate(sorted(entities))}
    return entity2id

def create_relation_mappings(data):
    relations = set()
    for edge in data['edges']:
        rel_type = edge.get('relationship')
        if rel_type is None:
            continue
        if rel_type.startswith('-'):
            rel_type = rel_type[1:]
        relations.add(rel_type)
    
    relation2id = {}
    id2relation = {}
    for idx, relation in enumerate(sorted(relations)):
        relation2id[relation] = idx
        id2relation[idx] = relation
    
    return relation2id, id2relation

def create_triplets(data, entity2id, relation2id):
    triplets = []
    
    for i, edge in enumerate(data['edges']):
        try:
            head = edge.get('source') or edge.get('from')
            tail = edge.get('target') or edge.get('to')
            rel_type = edge.get('relationship') or edge.get('type')
            
            if not all([head, tail, rel_type]):
                continue
                
            if head not in entity2id:
                continue
                
            if tail not in entity2id:
                continue
                
            if rel_type not in relation2id:
                continue
            
            triplets.append((
                entity2id[head],
                relation2id[rel_type],
                entity2id[tail]
            ))
            
        except Exception as e:
            continue
    return triplets

def split_data(triplets, id2relation, train_ratio=0.6, valid_ratio=0.2, test_ratio=0.2):
    rel_triplets = defaultdict(list)
    for t in triplets:
        rel_triplets[t[1]].append(t)
    
    train_triplets = []
    valid_triplets = []
    test_triplets = []
    for rel_id in rel_triplets:
        rel_name = id2relation[rel_id]
    
    for rel_id, rel_trips in rel_triplets.items():
        rel_name = id2relation[rel_id]
        if 'compatible_with' in rel_name:
            random.shuffle(rel_trips)
            n = len(rel_trips)
            
            n_train = int(n * train_ratio)
            n_valid = (n - n_train) // 2
            
            train_triplets.extend(rel_trips[:n_train])
            valid_triplets.extend(rel_trips[n_train:n_train + n_valid])
            test_triplets.extend(rel_trips[n_train + n_valid:])
        else:
            train_triplets.extend(rel_trips)
    
    return train_triplets, valid_triplets, test_triplets

def save_mappings_and_triplets(output_dir, entity2id, relation2id, train_triplets, valid_triplets, test_triplets):
    os.makedirs(output_dir, exist_ok=True)
    
    id2entity = {v: k for k, v in entity2id.items()}
    id2relation = {v: k for k, v in relation2id.items()}
    
    with open(os.path.join(output_dir, 'entities.txt'), 'w', encoding='utf-8') as f:
        for entity, idx in sorted(entity2id.items(), key=lambda x: x[1]):
            f.write(f'{entity}\t{idx}\n')
    
    with open(os.path.join(output_dir, 'relations.txt'), 'w', encoding='utf-8') as f:
        for relation, idx in sorted(relation2id.items(), key=lambda x: x[1]):
            f.write(f'{relation}\t{idx}\n')
    
    def save_triplets(triplets, filename):
        with open(os.path.join(output_dir, filename), 'w', encoding='utf-8') as f:
            for h, r, t in triplets:
                h_name = id2entity[h]
                r_name = id2relation[r]
                t_name = id2entity[t]
                f.write(f'{h_name}\t{r_name}\t{t_name}\n')
    
    save_triplets(train_triplets, 'train.txt')
    save_triplets(valid_triplets, 'valid.txt')
    save_triplets(test_triplets, 'test.txt')

def main():
    random.seed(42)
    input_file = 'augmented_knowledge_graph_new.json'
    output_dir = 'knowformer_data_augmented'
    data = load_json_data(input_file)
    entity2id = create_entity_mappings(data)
    relation2id, id2relation = create_relation_mappings(data)
    triplets = create_triplets(data, entity2id, relation2id)
    train_triplets, valid_triplets, test_triplets = split_data(triplets, id2relation)

    save_mappings_and_triplets(
        output_dir,
        entity2id,
        relation2id,
        train_triplets,
        valid_triplets,
        test_triplets
    )

if __name__ == '__main__':
    main() 