import os
import json
import networkx as nx
import requests
from typing import Dict, List, Set, Tuple
import re

class NexarClient:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.api_url = "https://api.nexar.com/graphql"
        self.token = None
        
    def _get_token(self):
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

    # def get_alternative_components(self, mpn: str) -> List[str]:
    #     query = """
    #     query ($mpn: String!) {
    #       supSearchMpn(q: $mpn) {
    #         results {
    #           part {
    #             similarParts {
    #               mpn
    #             }
    #           }
    #         }
    #       }
    #     }
    #     """
    #     variables = {"mpn": mpn}
    #     result = self._execute_query(query, variables)
    #     similar_parts = result["data"]["supSearchMpn"]["results"][0]["part"]["similarParts"]
    #     return [part["mpn"] for part in similar_parts[:5]] 

class ComponentDataGenerator:
    def __init__(self, client_id: str, client_secret: str):
        self.api = NexarClient(client_id, client_secret)
        self.graph = nx.Graph()
        self.cached_data = self._load_cached_data()
        
    def _load_cached_data(self) -> Dict: # to not waste API calls
        try:
            with open('component_cache.json', 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
            
    def _save_cached_data(self):
        with open('component_cache.json', 'w') as f:
            json.dump(self.cached_data, f, indent=2)

    def fetch_component_data(self, component_mpn: str, original_name: str) -> Dict:
        try:
            if original_name in self.cached_data:
                print(f"Using cached data for {original_name}")
                return self.cached_data[original_name]
                
            print(f"Fetching data for {component_mpn} ({original_name})")
            component_data = self.api.get_component_details(component_mpn)
            standardized_data = self._standardize_component_data(component_data)
            standardized_data['original_name'] = original_name
            
            self.cached_data[original_name] = standardized_data
            self._save_cached_data()
            
            return standardized_data
        except Exception as e:
            print(f"Error fetching data for {component_mpn}: {str(e)}")
            return None

    def _standardize_component_data(self, raw_data: Dict) -> Dict:
        specs = raw_data.get('specs', [])
        spec_dict = {spec['attribute']['name'].lower(): {'value': spec['value'], 'units': spec['units']} 
                    for spec in specs}
        
        descriptions = [desc['text'].lower() for desc in raw_data.get('descriptions', [])]
        description_text = ' '.join(descriptions)
        mpn = raw_data.get('mpn', '').lower()
        
        def get_component_type():
            type_indicators = {
                'mcu': ['pic', 'stm32', 'atmega', 'microcontroller'],
                'accelerometer': ['accelerometer', 'accel', 'imu', 'adxl', 'lsm6', 'mma'],
                'temp_sensor': ['temp', 'thermocouple', 'lm35', 'tmp', 'ds18'],
                'proximity': ['proximity', 'distance', 'hcsr04', 'vl53', 'gp2y'],
                'motor_driver': ['motor', 'driver', 'uln', 'drv', 'tmc', 'a4988'],
                'audio': ['audio', 'sound', 'amplifier', 'dac', 'codec', 'lm386'],
                'display': ['display', 'lcd', 'oled', 'led', 'st7'],
                'communication': ['ethernet', 'wifi', 'rf', 'wireless', 'can', 'spi', 'i2c']
            }
            
            text_to_check = description_text + ' ' + mpn
            for comp_type, indicators in type_indicators.items():
                if any(ind in text_to_check for ind in indicators):
                    return comp_type
            return 'misc'

        def parse_interface_from_description() -> List[str]:
            interfaces = []
            interface_keywords = {
                'i2c': 'I2C',
                'spi': 'SPI',
                'uart': 'UART',
                'i²c': 'I2C',
                'serial': 'Serial',
                'analog': 'Analog',
                'digital': 'Digital',
                'parallel': 'Parallel',
                'i2s': 'I2S',
                'onewire': 'OneWire',
                '1-wire': 'OneWire',
                'pwm': 'PWM',
                'can': 'CAN',
                'usb': 'USB',
                'modbus': 'Modbus',
                'rs232': 'RS232',
                'rs485': 'RS485'
            }
            
            comp_type = get_component_type()
            
            type_default_interfaces = {
                'mcu': ['Digital'],
                'accelerometer': ['Analog', 'I2C', 'SPI'],
                'temp_sensor': ['Analog', 'I2C'],
                'proximity': ['Analog', 'Digital'],
                'motor_driver': ['Digital', 'PWM'],
                'audio': ['Analog', 'I2S'],
                'display': ['SPI', 'I2C', 'Parallel'],
                'communication': ['SPI', 'I2C', 'UART']
            }
            
            for keyword, interface in interface_keywords.items():
                if keyword in description_text:
                    interfaces.append(interface)
            
            if not interfaces and comp_type in type_default_interfaces:
                interfaces.extend(type_default_interfaces[comp_type])
            
            return list(set(interfaces))
            
        def parse_voltage_from_description() -> Tuple[float, float]:
            min_v, max_v = 0.0, 0.0
            voltage_patterns = [
                r'(\d+(?:\.\d+)?)\s*v',  # matches "3.3v" or "5v"
                r'(\d+(?:\.\d+)?)\s*volt',  # matches "3.3 volt" or "5 volts"
                r'vdd\s*=?\s*(\d+(?:\.\d+)?)',  # matches "VDD=3.3" or "VDD 3.3"
                r'vcc\s*=?\s*(\d+(?:\.\d+)?)',  # matches "VCC=5" or "VCC 5"
            ]
            
            voltages = []
            for pattern in voltage_patterns:
                voltages.extend(re.findall(pattern, description_text))
            
            if voltages:
                voltages = [float(v) for v in voltages]
                min_v = min(voltages)
                max_v = max(voltages)
            
            # Set default voltage ranges based on component type
            comp_type = get_component_type()
            if not (min_v and max_v):
                type_default_voltages = {
                    'mcu': (3.0, 5.5),
                    'accelerometer': (3.0, 5.0),
                    'temp_sensor': (3.0, 5.5),
                    'proximity': (3.0, 5.5),
                    'motor_driver': (3.3, 12.0),
                    'audio': (3.3, 5.5),
                    'display': (3.3, 5.0),
                    'communication': (3.3, 5.0)
                }
                
                if comp_type in type_default_voltages:
                    min_v, max_v = type_default_voltages[comp_type]
            
            return min_v, max_v
            
        def parse_output_type_from_description() -> List[str]:
            """Parse output types from description and component type"""
            outputs = []
            output_keywords = {
                'analog output': 'Analog',
                'digital output': 'Digital',
                'differential': 'Differential',
                'single-ended': 'Single-ended',
                'open drain': 'Open-drain',
                'push-pull': 'Push-pull',
                'i2s': 'I2S',
                'pdm': 'PDM',
                'pwm': 'PWM',
                'current sink': 'Current-sink',
                'current source': 'Current-source',
                'ttl': 'TTL',
                'cmos': 'CMOS'
            }
            
            comp_type = get_component_type()
            type_default_outputs = {
                'mcu': ['Digital', 'TTL'],
                'accelerometer': ['Analog', 'Digital'],
                'temp_sensor': ['Analog', 'Digital'],
                'proximity': ['Analog', 'Digital'],
                'motor_driver': ['PWM', 'Digital'],
                'audio': ['Analog', 'Digital'],
                'display': ['Digital'],
                'communication': ['Digital']
            }
            
            # Add outputs from description
            for keyword, output in output_keywords.items():
                if keyword in description_text:
                    outputs.append(output)
            
            # Add default outputs if none found
            if not outputs and comp_type in type_default_outputs:
                outputs.extend(type_default_outputs[comp_type])
            
            return list(set(outputs))

        def parse_current_from_description() -> float:
            """Parse current consumption from description"""
            current_patterns = [
                r'(\d+(?:\.\d+)?)\s*ma',  # matches "100ma" or "0.1ma"
                r'(\d+(?:\.\d+)?)\s*a',   # matches "1a" or "0.5a"
                r'(\d+(?:\.\d+)?)\s*microamp',  # matches "100microamp"
                r'(\d+(?:\.\d+)?)\s*µa',  # matches "100µa"
            ]
            
            currents = []
            for pattern in current_patterns:
                matches = re.findall(pattern, description_text)
                for match in matches:
                    try:
                        current = float(match)
                        if 'ma' in pattern:
                            current *= 0.001
                        elif 'microamp' in pattern or 'µa' in pattern:
                            current *= 0.000001
                        currents.append(current)
                    except ValueError:
                        continue
            
            if currents:
                return max(currents)  # Return highest current found
                
            # Default currents based on component type
            comp_type = get_component_type()
            type_default_currents = {
                'mcu': 0.1,  # 100mA
                'accelerometer': 0.01,  # 10mA
                'temp_sensor': 0.005,  # 5mA
                'proximity': 0.02,  # 20mA
                'motor_driver': 1.0,  # 1A
                'audio': 0.05,  # 50mA
                'display': 0.1,  # 100mA
                'communication': 0.05  # 50mA
            }
            
            return type_default_currents.get(comp_type, 0.05)

        # Get interface from specs or description
        interface_spec = (
            spec_dict.get('interface', {}).get('value', '') or
            spec_dict.get('interface type', {}).get('value', '') or
            spec_dict.get('communication protocol', {}).get('value', '') or
            spec_dict.get('bus type', {}).get('value', '')
        )
        interfaces = (
            self._parse_list_value(interface_spec) or 
            parse_interface_from_description()
        )

        # Get voltage from specs or description
        min_v_spec = (
            spec_dict.get('min supply voltage', {}).get('value', '') or
            spec_dict.get('minimum supply voltage', {}).get('value', '') or
            spec_dict.get('voltage - supply, minimum', {}).get('value', '') or
            spec_dict.get('vdd min', {}).get('value', '')
        )
        max_v_spec = (
            spec_dict.get('max supply voltage', {}).get('value', '') or
            spec_dict.get('maximum supply voltage', {}).get('value', '') or
            spec_dict.get('voltage - supply, maximum', {}).get('value', '') or
            spec_dict.get('vdd max', {}).get('value', '')
        )
        
        min_v = self._parse_numeric(min_v_spec)
        max_v = self._parse_numeric(max_v_spec)
        if not (min_v and max_v):
            min_v, max_v = parse_voltage_from_description()

        # Get output type from specs or description
        output_spec = (
            spec_dict.get('output type', {}).get('value', '') or
            spec_dict.get('output', {}).get('value', '') or
            spec_dict.get('output format', {}).get('value', '') or
            spec_dict.get('output interface', {}).get('value', '')
        )
        outputs = (
            self._parse_list_value(output_spec) or 
            parse_output_type_from_description()
        )

        # Get current from specs or description
        current_spec = (
            spec_dict.get('supply current', {}).get('value', '') or
            spec_dict.get('current - supply', {}).get('value', '') or
            spec_dict.get('idd typical', {}).get('value', '') or
            spec_dict.get('current consumption', {}).get('value', '')
        )
        current = self._parse_numeric(current_spec) or parse_current_from_description()

        standardized = {
            'mpn': raw_data.get('mpn', ''),
            'manufacturer': raw_data.get('manufacturer', {}).get('name', ''),
            'descriptions': [desc['text'] for desc in raw_data.get('descriptions', [])],
            'interface': interfaces,
            'min_voltage': min_v,
            'max_voltage': max_v,
            'output_type': outputs,
            'supply_current': current,
            'component_type': get_component_type()
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
        processed_components = set()
        
        self.graph.add_node("3.3V", type="voltage", value=3.3)
        self.graph.add_node("5V", type="voltage", value=5.0)
        
        compatibility_map = {
            # Accelerometers
            'ADXL335': 'PIC18F4550-I/PT',
            'ADXL203': 'PIC18F4550-I/PT',
            'MMA7455L': 'PIC18F4550-I/PT',
            'LSM6DSO32': 'STM32H743ZIT6',
            'BMI088': 'STM32H743ZIT6',
            'ICM-42688-P': 'STM32H743ZIT6',
            'LSM6DSOX': 'STM32H743ZIT6',
            'MMA7361L': 'ATMEGA2560V-8AU',
            'ADXL377': 'ATMEGA2560V-8AU',
            'H3LIS331DL': 'ATMEGA2560V-8AU',
            
            # Temperature Sensors
            'LM35': 'PIC18F4550-I/PT',
            'TC74': 'PIC18F4550-I/PT',
            'MCP9700': 'PIC18F4550-I/PT',
            'TMP117': 'STM32H743ZIT6',
            'SHT40': 'STM32H743ZIT6',
            'HDC2080': 'STM32H743ZIT6',
            'MAX31855K': 'ATMEGA2560V-8AU',
            'DS18B20': 'ATMEGA2560V-8AU',
            'MAX6675': 'ATMEGA2560V-8AU',
            'MAX31856': 'ATMEGA2560V-8AU',
            
            # Proximity/Distance Sensors
            'GP2Y0A21YK': 'PIC18F4550-I/PT',
            'HCSR04': 'PIC18F4550-I/PT',
            'GP2Y0A02YK0F': 'PIC18F4550-I/PT',
            'VL53L1X': 'STM32H743ZIT6',
            'TMF8801': 'STM32H743ZIT6',
            'VL53L3CX': 'STM32H743ZIT6',
            'MB1013': 'ATMEGA2560V-8AU',
            'SRF05': 'ATMEGA2560V-8AU',
            'GP2Y0A710K0F': 'ATMEGA2560V-8AU',
            
            # Motors/Motor Controllers
            'ULN2003A': 'PIC18F4550-I/PT',
            'L293D': 'PIC18F4550-I/PT',
            'TB6612FNG': 'PIC18F4550-I/PT',
            'TMC5160': 'STM32H743ZIT6',
            'TMC4671': 'STM32H743ZIT6',
            'DRV8301': 'STM32H743ZIT6',
            'A4988': 'ATMEGA2560V-8AU',
            'DRV8825': 'ATMEGA2560V-8AU',
            'TB6600': 'ATMEGA2560V-8AU',
            
            # Audio Components
            'LM386': 'PIC18F4550-I/PT',
            'TDA2030': 'PIC18F4550-I/PT',
            'PAM8403': 'PIC18F4550-I/PT',
            'CS43L22': 'STM32H743ZIT6',
            'WM8960': 'STM32H743ZIT6',
            'ES8388': 'STM32H743ZIT6',
            'VS1053B': 'ATMEGA2560V-8AU',
            'MAX98357A': 'ATMEGA2560V-8AU',
            'UDA1334A': 'ATMEGA2560V-8AU',
            
            # Display Components
            'HD44780': 'PIC18F4550-I/PT',
            'PCD8544': 'PIC18F4550-I/PT',
            'ST7789': 'STM32H743ZIT6',
            'RA8875': 'STM32H743ZIT6',
            'ST7735': 'ATMEGA2560V-8AU',
            'MAX7219': 'ATMEGA2560V-8AU',
            
            # Communication Modules
            'MCP2515': 'PIC18F4550-I/PT',
            'ENC28J60': 'PIC18F4550-I/PT',
            'RFM69HW': 'PIC18F4550-I/PT',
            'W5500': 'STM32H743ZIT6',
            'ESP8266': 'STM32H743ZIT6',
            'NRF24L01': 'STM32H743ZIT6',
            'HC-12': 'ATMEGA2560V-8AU',
            'RFM95W': 'ATMEGA2560V-8AU',
            'SX1278': 'ATMEGA2560V-8AU',
            
            # Misc Components
            'MCP3002': 'PIC18F4550-I/PT',
            'DS1302': 'PIC18F4550-I/PT',
            'AT24C256': 'PIC18F4550-I/PT',
            'IS31FL3741': 'STM32H743ZIT6',
            'BMP388': 'STM32H743ZIT6',
            'MLX90640': 'STM32H743ZIT6',
            'DS1307': 'ATMEGA2560V-8AU',
            'HMC5883L': 'ATMEGA2560V-8AU',
            'MCP4725': 'ATMEGA2560V-8AU'
        }
        
        def get_existing_mpn(mpn: str) -> str:
            for node, data in self.graph.nodes(data=True):
                if data.get('mpn', '').lower() == mpn.lower():
                    return node
            return mpn

        def add_spec_edges(component_mpn: str, data: Dict):
            for interface in data.get('interface', []):
                if not interface:
                    continue
                if not self.graph.has_node(interface):
                    self.graph.add_node(interface, type="interface")
                self.graph.add_edge(component_mpn, interface, relationship="communicates_via")
            
            min_v = data.get('min_voltage', 0)
            max_v = data.get('max_voltage', 0)
            if min_v <= 3.3 <= max_v:
                self.graph.add_edge(component_mpn, "3.3V", relationship="requires_voltage")
            if min_v <= 5.0 <= max_v:
                self.graph.add_edge(component_mpn, "5V", relationship="requires_voltage")
            
            for output in data.get('output_type', []):
                if not output:
                    continue
                if not self.graph.has_node(output):
                    self.graph.add_node(output, type="output_type")
                self.graph.add_edge(component_mpn, output, relationship="outputs_as")
            
            if data.get('supply_current'):
                current_node = f"{data['supply_current']}mA"
                if not self.graph.has_node(current_node):
                    self.graph.add_node(current_node, type="current", value=data['supply_current'])
                self.graph.add_edge(component_mpn, current_node, relationship="draws_current")

        def process_component(mpn: str, original_name: str, process_alternatives: bool = True):
            existing_mpn = get_existing_mpn(mpn)
            if existing_mpn in processed_components:
                return existing_mpn
                
            data = self.fetch_component_data(mpn, original_name)
            if not data:
                return None

            self.graph.add_node(data['mpn'], type='component', **data)
            processed_components.add(data['mpn'])
   
            add_spec_edges(data['mpn'], data)

            if mpn in compatibility_map:
                compatible_mcu = compatibility_map[mpn]
                self.graph.add_edge(compatible_mcu, data['mpn'], relationship="compatible_with")

            if process_alternatives:
                alternatives = data.get('similarParts', [])[:5]
                for alt in alternatives:
                    alt_mpn = process_component(alt["mpn"], alt["mpn"], process_alternatives=False)
                    if alt_mpn:
                        self.graph.add_edge(data['mpn'], alt_mpn, relationship="alternative_for")

            return data['mpn']

        for component in component_list:
            if isinstance(component, tuple):
                mpn, _ = component
            else:
                mpn = component
            process_component(mpn, mpn, process_alternatives=True)

    def export_graph(self, output_path: str):
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
        
        with open(output_path, 'w') as f:
            json.dump(graph_data, f, indent=2)

def main():
    api_credentials = [
        {"client_id": "", 
         "client_secret": ""},
    ]
    
    current_api = 0
    generator = ComponentDataGenerator(
        api_credentials[current_api]["client_id"],
        api_credentials[current_api]["client_secret"]
    )
    
    components = [
        'PIC18F4550',          # 8-bit, 5V logic, limited interfaces
        'STM32H743ZIT6',       # 32-bit ARM, 3.3V logic, advanced features
        'ATMEGA2560',          # 8-bit, mixed voltage, intermediate features
        
        # Accelerometers
        'ADXL335',             # Analog output (PIC18F4550 compatible)
        'ADXL203',             # Analog dual-axis (PIC18F4550 compatible)
        'MMA7455L',            # Analog output (PIC18F4550 compatible)
        'LSM6DSO32',           # SPI/I2C, 3.3V only (STM32H743ZIT6 compatible)
        'BMI088',              # SPI/I2C, 3.3V (STM32H743ZIT6 compatible)
        'ICM-42688-P',         # SPI/I2C, 3.3V (STM32H743ZIT6 compatible)
        'LSM6DSOX',            # SPI/I2C, 3.3V (STM32H743ZIT6 compatible)
        'MMA7361L',            # Analog output (ATMEGA2560 compatible)
        'ADXL377',             # Analog high-g (ATMEGA2560 compatible)
        'H3LIS331DL',          # SPI (ATMEGA2560 compatible)
        
        # Temperature Sensors
        'LM35',                # Analog output (PIC18F4550 compatible)
        'TC74',                # Simple I2C (PIC18F4550 compatible)
        'MCP9700',             # Analog output (PIC18F4550 compatible)
        'TMP117',              # I2C only, 3.3V (STM32H743ZIT6 compatible)
        'SHT40',               # I2C only, 3.3V (STM32H743ZIT6 compatible)
        'HDC2080',             # I2C only, 3.3V (STM32H743ZIT6 compatible)
        'MAX31855K',           # SPI only (ATMEGA2560 compatible)
        'DS18B20',             # OneWire (ATMEGA2560 compatible)
        'MAX6675',             # SPI (ATMEGA2560 compatible)
        'MAX31856',            # SPI (ATMEGA2560 compatible)
        
        # Proximity/Distance Sensors
        'GP2Y0A21YK',          # Analog IR (PIC18F4550 compatible)
        'HCSR04',              # Digital pulse (PIC18F4550 compatible)
        'GP2Y0A02YK0F',        # Analog IR (PIC18F4550 compatible)
        'VL53L1X',             # I2C only, 3.3V (STM32H743ZIT6 compatible)
        'TMF8801',             # I2C only, 3.3V (STM32H743ZIT6 compatible)
        'VL53L3CX',            # I2C only, 3.3V (STM32H743ZIT6 compatible)
        'MB1013',              # Digital pulse (ATMEGA2560 compatible)
        'SRF05',               # Digital pulse (ATMEGA2560 compatible)
        'GP2Y0A710K0F',        # Analog IR (ATMEGA2560 compatible)
        
        # Motors/Motor Controllers
        'ULN2003A',            # Simple driver (PIC18F4550 compatible)
        'L293D',               # H-bridge (PIC18F4550 compatible)
        'TB6612FNG',           # DC motor driver (PIC18F4550 compatible)
        'TMC5160',             # SPI only, advanced (STM32H743ZIT6 compatible)
        'TMC4671',             # SPI only (STM32H743ZIT6 compatible)
        'DRV8301',             # SPI only (STM32H743ZIT6 compatible)
        'A4988',               # Mixed voltage (ATMEGA2560 compatible)
        'DRV8825',             # Stepper driver (ATMEGA2560 compatible)
        'TB6600',              # Stepper driver (ATMEGA2560 compatible)
        
        # Audio Components
        'LM386',               # Analog amp (PIC18F4550 compatible)
        'TDA2030',             # Audio amp (PIC18F4550 compatible)
        'PAM8403',             # Class-D amp (PIC18F4550 compatible)
        'CS43L22',             # I2S/I2C only (STM32H743ZIT6 compatible)
        'WM8960',              # I2S/I2C codec (STM32H743ZIT6 compatible)
        'ES8388',              # I2S audio codec (STM32H743ZIT6 compatible)
        'VS1053B',             # SPI with timing (ATMEGA2560 compatible)
        'MAX98357A',           # I2S amp (ATMEGA2560 compatible)
        'UDA1334A',            # I2S DAC (ATMEGA2560 compatible)
        
        # Display Components
        'HD44780',             # Parallel LCD (PIC18F4550 compatible)
        'PCD8544',             # SPI LCD (PIC18F4550 compatible)
        'ST7789',              # SPI, 3.3V (STM32H743ZIT6 compatible)
        'RA8875',              # SPI, 3.3V (STM32H743ZIT6 compatible)
        'ST7735',              # SPI LCD (ATMEGA2560 compatible)
        'MAX7219',             # SPI LED matrix (ATMEGA2560 compatible)
        
        # Communication Modules
        'MCP2515',             # CAN bus (PIC18F4550 compatible)
        'ENC28J60',            # Ethernet (PIC18F4550 compatible)
        'RFM69HW',             # RF module (PIC18F4550 compatible)
        'W5500',               # Ethernet, 3.3V (STM32H743ZIT6 compatible)
        'ESP8266',             # WiFi module (STM32H743ZIT6 compatible)
        'NRF24L01',            # RF, 3.3V (STM32H743ZIT6 compatible)
        'HC-12',               # UART RF (ATMEGA2560 compatible)
        'RFM95W',              # LoRa (ATMEGA2560 compatible)
        'SX1278',              # LoRa (ATMEGA2560 compatible)
        
        # Misc Components
        'MCP3002',             # Simple SPI ADC (PIC18F4550 compatible)
        'DS1302',              # RTC (PIC18F4550 compatible)
        'AT24C256',            # I2C EEPROM (PIC18F4550 compatible)
        'IS31FL3741',          # I2C LED matrix (STM32H743ZIT6 compatible)
        'BMP388',              # I2C pressure (STM32H743ZIT6 compatible)
        'MLX90640',            # I2C thermal array (STM32H743ZIT6 compatible)
        'DS1307',              # I2C timing (ATMEGA2560 compatible)
        'HMC5883L',            # I2C compass (ATMEGA2560 compatible)
        'MCP4725',             # I2C DAC (ATMEGA2560 compatible)
    ]
    
    generator.build_knowledge_graph(components)
    generator.export_graph('component_knowledge_graph_final.json')

if __name__ == "__main__":
    main()