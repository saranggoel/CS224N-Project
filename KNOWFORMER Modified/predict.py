import os
import json
import torch
from argparse import ArgumentParser

import pytorch_lightning as pl
from lightning import KnowformerLightningModule, TransductiveDataModule

def load_graph(json_path):
    with open(json_path, 'r') as f:
        graph = json.load(f)
    return graph['edges'], {node['id']: node.get('component_type', 'Unknown') for node in graph['nodes']}#, [node['id'] for node in graph['nodes']]

def get_node_name(test_set, n):
    if n in test_set:
        return "Test"
    return "NA"

def get_edge_name(edges, h, t):
    for edge in edges:
        if edge['source'] == h and edge['target'] == t:
            return edge['relationship']
    return "No"

def load_triplets(file_path):
    with open(file_path, 'r') as f:
        triplets = [line.strip().split() for line in f.readlines()]
    return triplets

def filter_predictions(predictions, source_node, target_node, component_types):
    filtered = []
    print(predictions)
    for pred in predictions:
        print(pred)
        if pred['relationship'] == 'compatible_with' and pred['source'] != source_node:
            continue
        if component_types.get(pred['target']) != component_types.get(target_node):
            continue
        filtered.append(pred)
    print(len(filtered))
    return filtered

def hits(ranks, num):
    cnt = 0
    for rank in ranks:
        if rank <= num:
            cnt += 1
    return cnt / len(ranks)

def mrr(ranks):
    sum = 0
    for rank in ranks:
        sum += 1 / rank
    return sum / len(ranks)

def mr(ranks):
    return sum(ranks) / len(ranks)

def print_rankings(triplets, predictions, component_types):
    for triplet in triplets:
        source, relation, target = triplet
        filtered_preds = filter_predictions(predictions, source, target, component_types)
        print(f"Query: {source} {relation} {target}")
        for rank, pred in enumerate(filtered_preds, start=1):
            print(f"Rank {rank}: {pred}")

def predict(args):
    hparams_path = os.path.join(os.path.dirname(args.checkpoint_path), 'hparams.json')
    with open(hparams_path, 'r') as f:
        hparams = json.load(f)
    
    edges, component_types = load_graph(args.graph_path)
    # print(edges)
    # print()
    # print(component_types)
    
    triplets = load_triplets('data/augmented/test.txt')
    
    datamodule = TransductiveDataModule(
        data_path=args.data_path,
        num_workers=args.num_workers,
        batch_size=hparams['batch_size'],
        test_batch_size=hparams['test_batch_size']
    )
    
    
    model = KnowformerLightningModule.load_from_checkpoint(
        args.checkpoint_path,
        num_relation=datamodule.num_relation,
        num_layer=hparams['num_layer'],
        num_qk_layer=hparams['num_qk_layer'],
        num_v_layer=hparams['num_v_layer'],
        hidden_dim=hparams['hidden_dim'],
        num_heads=hparams['num_heads'],
        drop=hparams['drop'],
        remove_all=hparams['remove_all'],
        loss_fn=hparams['loss_fn'],
        num_negative_sample=hparams['num_negative_sample'],
        optimizer=hparams['optimizer'],
        learning_rate=hparams['learning_rate'],
        weight_decay=hparams['weight_decay'],
        adversarial_temperature=hparams['adversarial_temperature']
    )
    model.eval()
    
    ranks = []
    for triplet in triplets:
        h, r, t = triplet
        h_id = datamodule.data_object.entity2id[h]
        r_id = datamodule.data_object.relation2id[r]
        t_id = datamodule.data_object.entity2id[t] if t else None
        
        query = torch.tensor([h_id, r_id, -1 if t_id is None else t_id])
        batch = [query]
    
        batch_data = datamodule.data_object.test_collate_fn(batch)

        with torch.no_grad():
            scores = model.model(batch_data)
        
        top_k = min(args.top_k, scores.shape[1])
        top_k = scores.shape[1]
        values, indices = torch.topk(scores[0], k=top_k)
        
        print(f"\nPredictions for: {h} {r} ?")
        print("\nTop", top_k, "predictions:")
        print("-" * 80)
        print("Entity                  Score       Edge Relationship       Component Type      Test Set Presence")
        print("-" * 80)

        test_set = ["MCP4725EV",
                    "MAX7219CWG+T",
                    "MCP9700DM-PCTL",
                    "ADXL203CE",
                    "D3172MMA7455L",
                    "TMP117MAIDRVR",
                    "WM8960CGEFL/RV",
                    "TB6612FNG,C,8,EL",
                    "TDA2030H",
                    "MCP2515DM-PTPLS",
                    "SHT40I-AD1B-R2",
                    "TMF8801-DB",
                    "DRV8301DCA",
                    "LM358DR2G",
                    "PAM8403DR"]
        cnt = 1
        for score, idx in zip(values, indices):
            entity = datamodule.data_object.id2entity[idx.item()]
            edge_name = get_edge_name(edges, h, entity)
            if edge_name == 'compatible_with':
                if entity != t:
                    continue
                rank = cnt
            if component_types.get(entity) != component_types.get(t):
                continue
            component_type = component_types.get(entity, "Unknown")
            test_presence = get_node_name(test_set, entity)
            print(f"{entity:<20} {score.item():>10.4f}       {edge_name:<20} {component_type}    {test_presence}")
            cnt += 1
        
        ranks.append(rank)
        if t_id is not None:
            t_score = scores[0, t_id]
            edge_name = get_edge_name(edges, h, t)
            component_type = component_types.get(t, "Unknown")

    print(f"Hits@1: {hits(ranks, 1)}")
    print(f"Hits@3: {hits(ranks, 3)}")
    print(f"Hits@5: {hits(ranks, 5)}")
    print(f"MRR: {mrr(ranks)}")
    print(f"MR: {mr(ranks)}")
    

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument('--checkpoint_path', type=str, required=True,
                        help='Path to the model checkpoint')
    parser.add_argument('--data_path', type=str, required=True,
                        help='Path to the dataset directory')
    parser.add_argument('--graph_path', type=str, required=True,
                        help='Path to the JSON file containing the graph edges')
    parser.add_argument('--top_k', type=int, default=5,
                        help='Number of top predictions to show')
    parser.add_argument('--num_workers', type=int, default=0,
                        help='Number of workers for data loading')
    args = parser.parse_args()
    predict(args)
