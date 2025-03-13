import torch
from torch import autograd

class RSPMMFunction(autograd.Function):
    @staticmethod
    def forward(ctx, edge_index, edge_type, edge_weight, relation, input, sum_type="add", mul_type="mul"):
        node_in, node_out = edge_index
        ctx.save_for_backward(edge_index, edge_type, edge_weight, relation, input)
        ctx.sum_type = sum_type
        ctx.mul_type = mul_type
        
        output = torch.zeros_like(input)
        for i in range(edge_index.size(1)):
            src, dst = edge_index[0, i], edge_index[1, i]
            rel = relation[edge_type[i]]
            weight = edge_weight[i]
            
            if mul_type == "mul":
                value = input[src] * rel
            else:  # add
                value = input[src] + rel
                
            value = value * weight
            
            if sum_type == "add":
                output[dst] += value
            elif sum_type == "min":
                if i == 0 or dst != edge_index[1, i-1]:
                    output[dst] = value
                else:
                    output[dst] = torch.min(output[dst], value)
            else:  # max
                if i == 0 or dst != edge_index[1, i-1]:
                    output[dst] = value
                else:
                    output[dst] = torch.max(output[dst], value)
        
        return output

    @staticmethod
    def backward(ctx, grad_output):
        edge_index, edge_type, edge_weight, relation, input = ctx.saved_tensors
        sum_type = ctx.sum_type
        mul_type = ctx.mul_type
        
        grad_weight = torch.zeros_like(edge_weight)
        grad_relation = torch.zeros_like(relation)
        grad_input = torch.zeros_like(input)
        
        for i in range(edge_index.size(1)):
            src, dst = edge_index[0, i], edge_index[1, i]
            rel = relation[edge_type[i]]
            weight = edge_weight[i]
            
            grad = grad_output[dst]
            
            if mul_type == "mul":
                grad_input[src] += grad * rel * weight
                grad_relation[edge_type[i]] += grad * input[src] * weight
            else:  # add
                grad_input[src] += grad * weight
                grad_relation[edge_type[i]] += grad * weight
            
            if sum_type in ["min", "max"]:
                # For min/max operations, we only propagate gradients through the selected path
                continue
                
            grad_weight[i] = torch.sum(grad * (input[src] * rel if mul_type == "mul" else input[src] + rel))
        
        # Return gradients for all input arguments:
        # edge_index, edge_type, edge_weight, relation, input, sum_type, mul_type
        return None, None, grad_weight, grad_relation, grad_input, None, None

def generalized_rspmm(edge_index, edge_type, edge_weight, relation, input, sum="add", mul="mul"):
    node_in, node_out = edge_index
    
    # Handle empty tensors
    if node_out.numel() == 0:
        # Return empty output tensor with same shape as input
        return torch.zeros_like(input)
    
    # Specify dimension for max operation
    key = node_in * (node_out.max(dim=0)[0] + 1) + node_out
    order = key.argsort()

    edge_index = edge_index[:, order]
    edge_type = edge_type[order]
    edge_weight = edge_weight[order]
    
    return RSPMMFunction.apply(edge_index, edge_type, edge_weight, relation, input, sum, mul)