import os
import json
import networkx as nx
import requests
from typing import Dict, List, Set, Tuple

class NexarClient:
    """Client for interacting with Nexar's GraphQL API"""
    
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.api_url = "https://api.nexar.com/graphql"
        self.token = None
        
    def _get_token(self):
        """Get authentication token from Nexar"""
        auth_url = "https://identity.nexar.com/connect/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        response = requests.post(auth_url, data=data)
        response.raise_for_status()
        self.token = response.json()["access_token"]
        
    def _execute_query(self, query: str, variables: Dict = None) -> Dict:
        """Execute GraphQL query"""
        if not self.token:
            self._get_token()
            
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(
            self.api_url,
            headers=headers,
            json={"query": query, "variables": variables}
        )
        response.raise_for_status()
        return response.json()

    def get_component_details(self, mpn: str) -> Dict:
        """Get component details and alternatives using Nexar's GraphQL API"""
        query = """
        query ($mpn: String!) {
          supSearchMpn(q: $mpn) {
            results {
              part {
                mpn
                manufacturer {
                  name
                }
                descriptions {
                  text
                }
                specs {
                  attribute {
                    name
                  }
                  value
                  units
                }
                bestDatasheet {
                  url
                }
                similarParts {
                  mpn
                }
              }
            }
          }
        }
        """
        variables = {"mpn": mpn}
        result = self._execute_query(query, variables)
        return result["data"]["supSearchMpn"]["results"][0]["part"]

    def get_alternative_components(self, mpn: str) -> List[str]:
        """Get alternative components for given MPN"""
        query = """
        query ($mpn: String!) {
          supSearchMpn(q: $mpn) {
            results {
              part {
                similarParts {
                  mpn
                }
              }
            }
          }
        }
        """
        variables = {"mpn": mpn}
        result = self._execute_query(query, variables)
        similar_parts = result["data"]["supSearchMpn"]["results"][0]["part"]["similarParts"]
        # Return only the first 5 alternatives
        return [part["mpn"] for part in similar_parts[:5]]

class ComponentDataGenerator:
    def __init__(self, client_id: str, client_secret: str):
        """Initialize the data generator with Nexar API credentials."""
        self.api = NexarClient(client_id, client_secret)
        self.graph = nx.Graph()
        
    def fetch_component_data(self, component_mpn: str) -> Dict:
        """Fetch detailed component data from Nexar API."""
        try:
            # Query Nexar API for component details
            component_data = self.api.get_component_details(component_mpn)
            return self._standardize_component_data(component_data)
        except Exception as e:
            print(f"Error fetching data for {component_mpn}: {str(e)}")
            return None

    def _standardize_component_data(self, raw_data: Dict) -> Dict:
        """Standardize component data format and units."""
        # Extract specifications we care about
        specs = raw_data.get('specs', [])
        spec_dict = {spec['attribute']['name']: {'value': spec['value'], 'units': spec['units']} 
                    for spec in specs}
        
        standardized = {
            'mpn': raw_data.get('mpn', ''),
            'manufacturer': raw_data.get('manufacturer', {}).get('name', ''),
            'descriptions': [desc['text'] for desc in raw_data.get('descriptions', [])],
            'interface': self._parse_list_value(spec_dict.get('Interface', {}).get('value', '')),
            'min_voltage': self._parse_numeric(spec_dict.get('Min Supply Voltage', {}).get('value', '')),
            'max_voltage': self._parse_numeric(spec_dict.get('Max Supply Voltage', {}).get('value', '')),
            'min_temp': spec_dict.get('Min Operating Temperature', {}).get('value', ''),
            'max_temp': spec_dict.get('Max Operating Temperature', {}).get('value', ''),
            'output_type': self._parse_list_value(spec_dict.get('Output Type', {}).get('value', '')),
            'supply_current': self._parse_numeric(spec_dict.get('Supply Current', {}).get('value', '')),
            'power_rating': spec_dict.get('Power Rating', {}).get('value', '')
        }
        return standardized

    def _parse_list_value(self, value: str) -> List[str]:
        """Parse comma-separated values into a list"""
        if not value:
            return []
        return [item.strip() for item in value.split(',')]

    def _parse_numeric(self, value: str) -> float:
        """Parse numeric value, handling units and converting to float"""
        if not value:
            return 0.0
        try:
            # Remove any non-numeric characters except decimal point
            numeric_str = ''.join(c for c in value if c.isdigit() or c == '.')
            return float(numeric_str)
        except ValueError:
            return 0.0

    def build_knowledge_graph(self, component_list: List[str]):
        """Build the knowledge graph from component data."""
        processed_components = set()
        component_cache = {}
        
        # Create standard voltage nodes
        self.graph.add_node("3.3V", type="voltage", value=3.3)
        self.graph.add_node("5V", type="voltage", value=5.0)
        
        def get_existing_mpn(mpn: str) -> str:
            """Check if component exists in graph under a different MPN"""
            for node, data in self.graph.nodes(data=True):
                if data.get('mpn', '').lower() == mpn.lower():
                    return node
            return mpn
        
        def add_spec_edges(component_mpn: str, data: Dict):
            """Add edges between component and its specification nodes"""
            # Add interface edges
            for interface in data.get('interface', []):
                if not interface:
                    continue
                # Create interface node if it doesn't exist
                if not self.graph.has_node(interface):
                    self.graph.add_node(interface, type="interface")
                self.graph.add_edge(component_mpn, interface, relationship="communicates_via")
            
            # Add voltage edges
            min_v = data.get('min_voltage', 0)
            max_v = data.get('max_voltage', 0)
            if min_v <= 3.3 <= max_v:
                self.graph.add_edge(component_mpn, "3.3V", relationship="requires_voltage")
            if min_v <= 5.0 <= max_v:
                self.graph.add_edge(component_mpn, "5V", relationship="requires_voltage")
            
            # Add output type edges
            for output in data.get('output_type', []):
                if not output:
                    continue
                # Create output type node if it doesn't exist
                if not self.graph.has_node(output):
                    self.graph.add_node(output, type="output_type")
                self.graph.add_edge(component_mpn, output, relationship="outputs_as")
            
            # Add supply current as node if specified
            if data.get('supply_current'):
                current_node = f"{data['supply_current']}mA"
                if not self.graph.has_node(current_node):
                    self.graph.add_node(current_node, type="current", value=data['supply_current'])
                self.graph.add_edge(component_mpn, current_node, relationship="draws_current")

        def process_component(mpn: str, process_alternatives: bool = True):
            """Helper function to process a component and optionally its alternatives"""
            existing_mpn = get_existing_mpn(mpn)
            if existing_mpn in processed_components:
                return existing_mpn
                
            if mpn in component_cache:
                data = component_cache[mpn]
            else:
                raw_data = self.api.get_component_details(mpn)
                if not raw_data:
                    return None
                data = self._standardize_component_data(raw_data)
                component_cache[mpn] = data

            # Add component node
            self.graph.add_node(data['mpn'], type='component', **data)
            processed_components.add(data['mpn'])
            
            # Add specification edges
            add_spec_edges(data['mpn'], data)

            if process_alternatives:
                alternatives = [part["mpn"] for part in raw_data.get("similarParts", [])][:5]
                for alt in alternatives:
                    alt_mpn = process_component(alt, process_alternatives=False)
                    if alt_mpn:
                        self.graph.add_edge(data['mpn'], alt_mpn, relationship='alternative_for')

            return data['mpn']

        # Process each component in the initial list
        for component in component_list:
            process_component(component, process_alternatives=False)

    def add_compatibility_edges(self, compatibility_data: List[Tuple[str, str]]):
        """Add known compatibility edges to the graph."""
        for comp1, comp2 in compatibility_data:
            if comp1 in self.graph.nodes and comp2 in self.graph.nodes:
                self.graph.add_edge(comp1, comp2, relationship='compatible_with')

    def export_graph(self, output_path: str):
        """Export the knowledge graph to a JSON file."""
        # Convert graph to dictionary format
        graph_data = {
            'nodes': [
                {
                    'id': node,
                    'type': data.get('type', ''),
                    **{k:v for k,v in data.items() if k != 'type'}
                }
                for node, data in self.graph.nodes(data=True)
            ],
            'edges': [
                {
                    'source': u,
                    'target': v,
                    'relationship': data.get('relationship', '')
                }
                for u, v, data in self.graph.edges(data=True)
            ]
        }
        
        # Save as JSON
        with open(output_path, 'w') as f:
            json.dump(graph_data, f, indent=2)

def main():
    client_id = "" # Add your own credentials
    client_secret = "" # Add your own credentials
    generator = ComponentDataGenerator(client_id, client_secret)
    
    # Example component list
    components = [
        # Microcontrollers
        'PIC18F4550',          # 8-bit, 5V logic, limited interfaces
        'STM32H743ZIT6',       # 32-bit ARM, 3.3V logic, advanced features
        'ATMEGA2560',          # 8-bit, mixed voltage, intermediate features
        
        # Accelerometers
        'ADXL335',             # Analog output (PIC18F4550 compatible)
        'LSM6DSO32',           # SPI/I2C, 3.3V only (STM32H743ZIT6 compatible)
        'MMA7361L',            # Analog output (ATMEGA2560 compatible)
        
        # Temperature Sensors
        'LM35',                # Analog output (PIC18F4550 compatible)
        'TMP117',              # I2C only, 3.3V (STM32H743ZIT6 compatible)
        'MAX31855K',           # SPI only (ATMEGA2560 compatible)
        
        # Proximity/Distance Sensors
        'GP2Y0A21YK',         # Analog IR (PIC18F4550 compatible)
        'VL53L1X',            # I2C only, 3.3V (STM32H743ZIT6 compatible)
        'MB1013',             # Digital pulse (ATMEGA2560 compatible)
        
        # Motors/Motor Controllers
        'ULN2003A',           # Simple driver (PIC18F4550 compatible)
        'TMC5160',            # SPI only, advanced (STM32H743ZIT6 compatible)
        'A4988',              # Mixed voltage (ATMEGA2560 compatible)
        
        # Audio Components
        'LM386',              # Analog amp (PIC18F4550 compatible)
        'CS43L22',            # I2S/I2C only (STM32H743ZIT6 compatible)
        'VS1053B',            # SPI with specific timing (ATMEGA2560 compatible)
        
        # Misc Components
        'MCP3002',            # Simple SPI ADC (PIC18F4550 compatible)
        'IS31FL3741',         # I2C LED matrix driver (STM32H743ZIT6 compatible)
        'DS1307',             # Specific I2C timing (ATMEGA2560 compatible)
    ]
    
    # Build the knowledge graph
    generator.build_knowledge_graph(components)
    
    # Add subset of known compatibility edges
    compatibility_data = [
        ('LM386MMX-1/NOPB', 'PIC18F4550-I/PT'),
        ('MB1013-000','ATMEGA2560V-8AU'),
        ('TMP117MAIDRVR','STM32H743ZIT6'),
        ('GP2Y0A21YK0F','PIC18F4550-I/PT'),
        ('VL53L1X-SATEL','STM32H743ZIT6'),
        ('A4988SETTR-T','ATMEGA2560V-8AU'),
    ]
    generator.add_compatibility_edges(compatibility_data)
    
    # Export the graph as JSON
    generator.export_graph('component_knowledge_graph_milestone.json')

if __name__ == "__main__":
    main()