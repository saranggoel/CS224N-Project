from pyvis.network import Network
import json
import random

def load_graph(json_path):
    with open(json_path, 'r') as f:
        data = json.load(f)
    return data

def create_visualization(graph_data, output_path='graph_milestone.html'):
    # Create network with explicit notebook mode off
    net = Network(height='750px', width='100%', notebook=False, bgcolor='#ffffff', font_color='#000000')
    
    # Define color scheme
    colors = {
        'component': '#6BAED6',      # Blue for components
        'interface': '#74C476',      # Green for interfaces
        'voltage': '#FD8D3C',        # Orange for voltage
        'output_type': '#9E9AC8',    # Purple for output types
        'current': '#969696'         # Gray for current
    }
    
    # Define edge colors and their meanings
    edge_colors = {
        'alternative_for': '#ff0000',      # Red
        'communicates_via': '#00ff00',     # Green
        'requires_voltage': '#ffa500',     # Orange
        'outputs_as': '#800080',           # Purple
        'draws_current': '#666666',        # Gray
        'compatible_with': '#0000ff'       # Blue
    }

    # Create HTML for the legend
    legend_html = """
    <div class="legend" style="position: absolute; top: 10px; left: 10px; 
        background-color: rgba(255, 255, 255, 0.8); padding: 10px; border-radius: 5px; 
        border: 1px solid #ccc; font-family: Arial; z-index: 1000;">
        <h3 style="margin: 0 0 10px 0;">Legend</h3>
        <div style="display: flex; flex-direction: column; gap: 5px;">
    """
    
    # Add node types to legend
    legend_html += "<h4 style='margin: 5px 0;'>Node Types:</h4>"
    for node_type, color in colors.items():
        legend_html += f"""
        <div style="display: flex; align-items: center; gap: 5px;">
            <div style="width: 20px; height: 20px; background-color: {color}; 
                border-radius: 50%;"></div>
            <span>{node_type.replace('_', ' ').title()}</span>
        </div>
        """
    
    # Add edge types to legend
    legend_html += "<h4 style='margin: 10px 0 5px 0;'>Edge Types:</h4>"
    for edge_type, color in edge_colors.items():
        legend_html += f"""
        <div style="display: flex; align-items: center; gap: 5px;">
            <div style="width: 30px; height: 3px; background-color: {color};"></div>
            <span>{edge_type.replace('_', ' ').title()}</span>
        </div>
        """
    
    legend_html += "</div></div>"

    # Add nodes
    for node in graph_data['nodes']:
        # Set node properties based on type
        node_type = node.get('type', '')
        color = colors.get(node_type, '#000000')
        
        # Adjust size based on node type
        size = 20
        if node_type == 'component':
            size = 30
        elif node_type in ['voltage', 'interface']:
            size = 25
            
        # Create label
        if node_type == 'component':
            label = f"{node['mpn']}\n{node['manufacturer']}"
        else:
            label = node['id']
            
        # Create title (hover text)
        title = ''
        if node_type == 'component':
            title = f"MPN: {node['mpn']}\n"
            title += f"Manufacturer: {node['manufacturer']}\n"
            if node.get('descriptions'):
                title += f"Description: {node['descriptions'][0]}\n"
            if node.get('interface'):
                title += f"Interfaces: {', '.join(node['interface'])}\n"
            if node.get('min_voltage') and node.get('max_voltage'):
                title += f"Voltage Range: {node['min_voltage']}V - {node['max_voltage']}V\n"
        
        net.add_node(node['id'], 
                    label=label, 
                    color=color,
                    title=title,
                    size=size)
    
    # Add edges with different colors based on relationship
    for edge in graph_data['edges']:
        color = edge_colors.get(edge['relationship'], '#000000')
        net.add_edge(edge['source'], 
                    edge['target'], 
                    color=color, 
                    title=edge['relationship'],
                    smooth=True)
    
    # Configure physics and other options
    net.set_options("""
    {
      "physics": {
        "forceAtlas2Based": {
          "gravitationalConstant": -100,
          "centralGravity": 0.01,
          "springLength": 200,
          "springConstant": 0.08
        },
        "maxVelocity": 50,
        "minVelocity": 0.1,
        "solver": "forceAtlas2Based",
        "timestep": 0.35
      },
      "interaction": {
        "hover": true,
        "tooltipDelay": 300,
        "navigationButtons": true,
        "keyboard": true,
        "zoomView": true
      },
      "edges": {
        "smooth": {
          "type": "continuous",
          "forceDirection": "none"
        }
      },
      "layout": {
        "improvedLayout": true,
        "hierarchical": {
          "enabled": false
        }
      }
    }
    """)

    # Generate HTML file with legend
    html_content = net.generate_html()
    html_with_legend = html_content.replace('</body>', f'{legend_html}</body>')
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_with_legend)
    print(f"Graph saved to {output_path}")

def main():
    try:
        # Load the graph data
        graph_data = load_graph('component_knowledge_graph_milestone.json')
        
        # Create the visualization
        create_visualization(graph_data)
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    main() 