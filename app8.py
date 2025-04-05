import pygame
import pygame_gui
import numpy as np
from collections import defaultdict

# Constants
WINDOW_WIDTH = 1024
WINDOW_HEIGHT = 768
ROAD_WIDTH = 120
LANE_WIDTH = 30
INTERSECTION_SIZE = 100
VEHICLE_LENGTH = 40
VEHICLE_WIDTH = 20
LIGHT_RADIUS = 8

# Traffic light timing constants
MIN_GREEN_TIME = 10
MAX_GREEN_TIME = 30
YELLOW_TIME = 3

# Junction sides configuration
JUNCTION_SIDES = {
    'N': {'position_offset': (0, -1), 'lanes': 2},
    'S': {'position_offset': (0, 1), 'lanes': 2},
    'E': {'position_offset': (1, 0), 'lanes': 2},
    'W': {'position_offset': (-1, 0), 'lanes': 2}
}

# Vehicle types with their properties
VEHICLE_TYPES = {
    'Car': {'length': 40, 'width': 20, 'speed': 3, 'color': (255, 0, 0)},
    'Bus': {'length': 60, 'width': 25, 'speed': 2, 'color': (0, 0, 255)},
    'Truck': {'length': 70, 'width': 25, 'speed': 2, 'color': (128, 0, 128)},
    'Motorcycle': {'length': 30, 'width': 15, 'speed': 4, 'color': (255, 165, 0)}
}

class Lane:
    def __init__(self, junction_id, side, lane_number, position):
        self.junction_id = junction_id
        self.side = side
        self.lane_number = lane_number
        self.position = position
        self.vehicles = []
        self.spacing = 5
        
        # Get junction centers
        junction0_y = WINDOW_HEIGHT//2
        junction1_y = WINDOW_HEIGHT//2
        junction0_x = WINDOW_WIDTH//3
        junction1_x = 2*WINDOW_WIDTH//3
        
        # Determine direction based on side and lane number
        # For E/W: Lane 1 goes East, Lane 2 goes West
        # For N/S: Lane 1 goes South, Lane 2 goes North
        if self.side == 'N':
            self.direction = 'S'  # Vehicles from North move South (into junction)
        elif self.side == 'S':
            self.direction = 'N'  # Vehicles from South move North (into junction)
        elif self.side == 'E':
            self.direction = 'W'  # Vehicles from East move West
        else:  # West side
            self.direction = 'E'  # Vehicles from West move East
        
        # Set spawn points based on lane number, side, and junction
        if side == 'W':  # West side lanes
            if junction_id == 0:
                self.spawn_point = [100, position[1]]  # Left edge for Junction 0
            else:
                self.spawn_point = [junction0_x + 100, position[1]]  # Middle point for Junction 1
        elif side == 'E':  # East side lanes
            if junction_id == 0:
                self.spawn_point = [junction1_x - 100, position[1]]  # Middle point for Junction 0
            else:
                self.spawn_point = [WINDOW_WIDTH - 100, position[1]]  # Right edge for Junction 1
        elif side == 'N':  # North side lanes
            if junction_id == 0 or junction_id == 1:
                self.spawn_point = [position[0], 100]  # Top edge
        elif side == 'S':  # South side lanes
            if junction_id == 0 or junction_id == 1:
                self.spawn_point = [position[0], WINDOW_HEIGHT - 100]  # Bottom edge
            
    def place_vehicle(self, vehicle_type):
        # Validate vehicle placement based on lane configuration
        # For each side, only allow placement in lanes that lead to the junction
        if self.side == 'W' and self.lane_number != 0:  # West side: only Lane 1 (moving East)
            return False
        if self.side == 'E' and self.lane_number != 1:  # East side: only Lane 2 (moving West)
            return False
        if self.side == 'N' and self.lane_number != 0:  # North side: only Lane 1 (moving South)
            return False
        if self.side == 'S' and self.lane_number != 1:  # South side: only Lane 2 (moving North)
            return False
            
        vehicle_length = VEHICLE_TYPES[vehicle_type]['length']
        base_position = list(self.spawn_point)
        
        # Calculate offset based on existing vehicles
        total_offset = sum([VEHICLE_TYPES[v.type]['length'] + self.spacing for v in self.vehicles])
        
        # Adjust position based on direction
        if self.direction == 'E':  # Left to Right
            base_position[0] += total_offset
        elif self.direction == 'W':  # Right to Left
            base_position[0] -= total_offset
        elif self.direction == 'S':  # Top to Bottom
            base_position[1] += total_offset
        elif self.direction == 'N':  # Bottom to Top
            base_position[1] -= total_offset
            
        vehicle = Vehicle(base_position, self.direction, vehicle_type)
        self.vehicles.append(vehicle)
        return True
        
    def update(self, dt, traffic_light_state):
        for i, vehicle in enumerate(self.vehicles):
            # Check if there's a vehicle ahead
            min_distance = VEHICLE_TYPES[vehicle.type]['length'] + self.spacing
            can_move_forward = True
            
            if i > 0:  # If not the first vehicle
                vehicle_ahead = self.vehicles[i-1]
                if self.direction in ['E', 'W']:
                    distance = abs(vehicle_ahead.position[0] - vehicle.position[0])
                else:  # N, S directions
                    distance = abs(vehicle_ahead.position[1] - vehicle.position[1])
                
                if distance < min_distance:
                    can_move_forward = False
            
            # Only move if light is green and path is clear
            should_move = traffic_light_state == 'green' and can_move_forward
            vehicle.update(dt, should_move)
            
        # Remove vehicles that have moved off screen
        self.vehicles = [v for v in self.vehicles if not v.is_off_screen()]

class TrafficLight:
    def __init__(self, position, direction, junction_id):
        self.position = position
        self.direction = direction
        self.junction_id = junction_id
        self.state = 'red'
        self.timer = 0
        self.min_green_time = 10  # Minimum green time
        self.max_green_time = 45  # Maximum green time
        self.yellow_time = 3
        self.current_cycle_time = self.min_green_time
        self.countdown_active = False
        self.vehicle_count_last_cycle = 0
        self.vehicles_cleared_last_cycle = 0
        self.performance_history = []  # Track timing effectiveness
        
    def calculate_green_time(self, vehicle_count, approaching_count=0):
        """Calculate adaptive green time based on vehicle density"""
        base_time = self.min_green_time
        
        # Add time based on current vehicle count
        density_factor = min(vehicle_count * 3, 20)  # Cap density factor
        
        # Consider approaching vehicles for E/W directions
        if self.direction in ['E', 'W']:
            approach_factor = min(approaching_count * 2, 10)
        else:
            approach_factor = 0
            
        # Use historical performance to adjust timing
        avg_performance = self.get_average_performance()
        performance_adjustment = self.calculate_performance_adjustment(avg_performance)
        
        total_time = base_time + density_factor + approach_factor + performance_adjustment
        return min(max(total_time, self.min_green_time), self.max_green_time)
    
    def get_average_performance(self):
        """Calculate average performance from history"""
        if not self.performance_history:
            return 1.0
        return sum(self.performance_history) / len(self.performance_history)
    
    def calculate_performance_adjustment(self, avg_performance):
        """Calculate timing adjustment based on historical performance"""
        if avg_performance < 0.7:  # Poor clearance rate
            return 5  # Add more time
        elif avg_performance > 0.9:  # Excellent clearance rate
            return -3  # Reduce time
        return 0
    
    def update_performance(self, vehicles_cleared, total_vehicles):
        """Update performance metrics after each cycle"""
        if total_vehicles > 0:
            performance = vehicles_cleared / total_vehicles
            self.performance_history.append(performance)
            # Keep last 5 cycles
            if len(self.performance_history) > 5:
                self.performance_history.pop(0)
    
    def start_cycle(self, vehicle_count, approaching_count=0):
        """Start a new traffic light cycle"""
        self.current_cycle_time = self.calculate_green_time(vehicle_count, approaching_count)
        self.timer = self.current_cycle_time
        self.countdown_active = True
        self.vehicle_count_last_cycle = vehicle_count
        self.vehicles_cleared_last_cycle = 0
        
    def update(self, dt, vehicles_present=False, current_vehicle_count=0):
        if not vehicles_present and self.state != 'red':
            # Update performance before changing state
            self.update_performance(self.vehicles_cleared_last_cycle,
                                  self.vehicle_count_last_cycle)
            self.state = 'red'
            self.timer = 0
            self.countdown_active = False
            return

        if self.timer > 0 and self.countdown_active:
            self.timer -= dt
            
            # Track cleared vehicles
            if self.state == 'green':
                vehicles_cleared = self.vehicle_count_last_cycle - current_vehicle_count
                if vehicles_cleared > self.vehicles_cleared_last_cycle:
                    self.vehicles_cleared_last_cycle = vehicles_cleared
            
            if self.timer <= 0:
                if self.state == 'green':
                    self.state = 'yellow'
                    self.timer = self.yellow_time
                elif self.state == 'yellow':
                    self.state = 'red'
                    self.timer = 0
                    # Update performance at end of cycle
                    self.update_performance(self.vehicles_cleared_last_cycle,
                                         self.vehicle_count_last_cycle)
    def draw(self, screen):
        x, y = self.position
        pygame.draw.rect(screen, (50, 50, 50), (x-10, y-30, 20, 60))
        
        red_pos = (x, y-20)
        yellow_pos = (x, y)
        green_pos = (x, y+20)
        
        red_color = (255, 0, 0) if self.state == 'red' else (50, 0, 0)
        yellow_color = (255, 255, 0) if self.state == 'yellow' else (50, 50, 0)
        green_color = (0, 255, 0) if self.state == 'green' else (0, 50, 0)
        
        pygame.draw.circle(screen, red_color, red_pos, LIGHT_RADIUS)
        pygame.draw.circle(screen, yellow_color, yellow_pos, LIGHT_RADIUS)
        pygame.draw.circle(screen, green_color, green_pos, LIGHT_RADIUS)
        
        if self.timer > 0 and self.countdown_active:
            font = pygame.font.Font(None, 24)
            timer_text = font.render(f"{int(self.timer)}s", True, (255, 255, 255))
            screen.blit(timer_text, (x+15, y-10))
            
            
class Intersection:
    def __init__(self, position, id):
        self.position = position
        self.id = id
        self.lights = {}
        self.lanes = {}
        self.setup_lights_and_lanes()
        self.lane_densities = defaultdict(float)
        self.green_time = MIN_GREEN_TIME
        
    def setup_lights_and_lanes(self):
        for side, config in JUNCTION_SIDES.items():
            # Setup traffic lights
            offset_x = config['position_offset'][0] * INTERSECTION_SIZE//2
            offset_y = config['position_offset'][1] * INTERSECTION_SIZE//2
            light_pos = (self.position[0] + offset_x, self.position[1] + offset_y)
            self.lights[side] = TrafficLight(light_pos, side, self.id)
            
            # Setup lanes for each side
            self.lanes[side] = []
            for lane_num in range(config['lanes']):
                lane_offset = LANE_WIDTH * (lane_num - (config['lanes']-1)/2)
                if side in ['N', 'S']:
                    lane_pos = (self.position[0] + lane_offset,
                              self.position[1] + offset_y * 1.5)
                else:
                    lane_pos = (self.position[0] + offset_x * 1.5,
                              self.position[1] + lane_offset)
                self.lanes[side].append(Lane(self.id, side, lane_num, lane_pos))
        
    def set_timing(self, green_time):
        self.green_time = max(MIN_GREEN_TIME, min(MAX_GREEN_TIME, green_time))
        
    def update_lights(self, states, cycle_time=None):
        for side, state in states.items():
            self.lights[side].state = state
            if cycle_time is not None and state == 'green':
                self.lights[side].cycle_time = cycle_time
                self.lights[side].timer = cycle_time
        
    def draw(self, screen):
        # Draw intersection background
        x, y = self.position
        pygame.draw.rect(screen, (80, 80, 80),
                        (x-INTERSECTION_SIZE//2, y-INTERSECTION_SIZE//2,
                         INTERSECTION_SIZE, INTERSECTION_SIZE))
        
        # Draw traffic lights
        for light in self.lights.values():
            light.draw(screen)
            
        # Draw lanes and vehicles
        for side_lanes in self.lanes.values():
            for lane in side_lanes:
                # Draw lane marker
                pygame.draw.circle(screen, (255, 255, 255),
                                 (int(lane.position[0]), int(lane.position[1])), 3)
                # Draw all vehicles in the lane
                for vehicle in lane.vehicles:
                    vehicle.draw(screen)
class Vehicle:
    def __init__(self, position, direction, vehicle_type='Car'):
        self.position = list(position)
        self.direction = direction
        self.type = vehicle_type
        self.properties = VEHICLE_TYPES[self.type]
        self.speed = self.properties['speed']
        self.color = self.properties['color']
        self.stopped = False
        self.label = ""
        
    def update(self, dt, can_move):
        if not can_move:
            return
            
        if self.direction == 'E':
            self.position[0] += self.speed
        elif self.direction == 'W':
            self.position[0] -= self.speed
        elif self.direction == 'S':
            self.position[1] += self.speed
        elif self.direction == 'N':
            self.position[1] -= self.speed
            
    def is_off_screen(self):
        return (self.direction == 'E' and self.position[0] > WINDOW_WIDTH + 100) or \
               (self.direction == 'W' and self.position[0] < -100) or \
               (self.direction == 'S' and self.position[1] > WINDOW_HEIGHT + 100) or \
               (self.direction == 'N' and self.position[1] < -100)
        
    def draw(self, screen):
        x, y = self.position
        length = self.properties['length']
        width = self.properties['width']
        
        # Draw vehicle with proper orientation
        if self.direction in ['E', 'W']:
            rect = pygame.Rect(x - length//2, y - width//2, length, width)
        else:  # N, S directions
            rect = pygame.Rect(x - width//2, y - length//2, width, length)
        pygame.draw.rect(screen, self.color, rect)
        
        # Draw label if present
        if self.label:
            font = pygame.font.Font(None, 20)
            text = font.render(self.label, True, (255, 255, 255))
            text_rect = text.get_rect(center=(x, y - max(width, length) - 10))
            screen.blit(text, text_rect)
            
            
def calculate_green_time(vehicle_count, is_inter_junction=False):
    """Calculate green time based on vehicle count."""
    if is_inter_junction:
        base_time = 15
        per_vehicle_time = 3
    else:
        base_time = 10
        per_vehicle_time = 2
        
    additional_time = vehicle_count * per_vehicle_time
    return min(base_time + additional_time, MAX_GREEN_TIME)


def is_vehicle_between_junctions(vehicle_position, direction):
    """Check if a vehicle is traveling between junctions."""
    junction0_x = WINDOW_WIDTH // 3
    junction1_x = 2 * WINDOW_WIDTH // 3
    
    if direction == 'E':  # Moving from junction 0 to 1 (Lane 1)
        return junction0_x < vehicle_position[0] < junction1_x
    elif direction == 'W':  # Moving from junction 1 to 0 (Lane 2)
        return junction1_x > vehicle_position[0] > junction0_x
    
    return False
    
    
class TrafficSystem:
    def __init__(self, manager):
        self.manager = manager
        self.intersections = [
            Intersection((WINDOW_WIDTH//3, WINDOW_HEIGHT//2), 0),
            Intersection((2*WINDOW_WIDTH//3, WINDOW_HEIGHT//2), 1)
        ]
        self.setup_gui()
        self.simulation_started = False
        self.font = pygame.font.Font(None, 24)
        self.timing_window = None
        # To store the timing window reference
        
    def setup_intersections(self):
        self.intersections = [
            Intersection((WINDOW_WIDTH//3, WINDOW_HEIGHT//2), 0),
            Intersection((2*WINDOW_WIDTH//3, WINDOW_HEIGHT//2), 1)
        ]
        
    def setup_gui(self):
        # Previous GUI elements with adjusted positions
        self.junction_dropdown = pygame_gui.elements.UIDropDownMenu(
            options_list=['Junction 0', 'Junction 1'],
            starting_option='Junction 0',
            relative_rect=pygame.Rect((20, 20), (120, 30)),
            manager=self.manager
        )
        
        self.side_dropdown = pygame_gui.elements.UIDropDownMenu(
            options_list=['North', 'South', 'East', 'West'],
            starting_option='North',
            relative_rect=pygame.Rect((150, 20), (100, 30)),
            manager=self.manager
        )
        
        self.lane_dropdown = pygame_gui.elements.UIDropDownMenu(
            options_list=['Lane 1', 'Lane 2'],
            starting_option='Lane 1',
            relative_rect=pygame.Rect((260, 20), (100, 30)),
            manager=self.manager
        )
        
        self.vehicle_dropdown = pygame_gui.elements.UIDropDownMenu(
            options_list=list(VEHICLE_TYPES.keys()),
            starting_option=list(VEHICLE_TYPES.keys())[0],
            relative_rect=pygame.Rect((370, 20), (120, 30)),
            manager=self.manager
        )
        
        # Adjusted button positions and sizes
        self.add_vehicle_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect((500, 20), (90, 30)),
            text='Add Vehicle',
            manager=self.manager
        )
        
        self.start_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect((600, 20), (70, 30)),
            text='Start',
            manager=self.manager
        )
        
        self.check_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect((680, 20), (70, 30)),
            text='Check',
            manager=self.manager
        )
        
        # Add new Reset button
        self.reset_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect((760, 20), (70, 30)),
            text='Reset',
            manager=self.manager
        )
        
        # Adjust status label position
        self.status_label = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect((840, 20), (170, 30)),
            text="Select junction, side, lane and vehicle",
            manager=self.manager
        )


    def show_timing_info(self):
        if self.timing_window:
            self.timing_window.kill()

        self.timing_window = pygame_gui.elements.UIWindow(
            rect=pygame.Rect((50, 100), (600, 500)),
            manager=self.manager,
            window_display_title="Traffic Flow Timing Analysis"
        )

        # Calculate current densities and expected timings
        timing_data = []
        
        # Header for the HTML table
        table_html = """
        <body style='line-height: 1.5'>
        <table style='width: 100%; border-collapse: collapse;'>
            <tr style='background-color: #4a4a4a;'>
                <th style='border: 1px solid #ddd; padding: 8px; text-align: left;'>Junction</th>
                <th style='border: 1px solid #ddd; padding: 8px; text-align: left;'>Direction</th>
                <th style='border: 1px solid #ddd; padding: 8px; text-align: left;'>Vehicle Count</th>
                <th style='border: 1px solid #ddd; padding: 8px; text-align: left;'>Expected Green Time</th>
                <th style='border: 1px solid #ddd; padding: 8px; text-align: left;'>Current State</th>
            </tr>
        """

        for i, intersection in enumerate(self.intersections):
            # Calculate EW traffic (including approaching vehicles)
            next_junction = self.intersections[1 if i == 0 else 0]
            approaching_count = sum(
                1 for side in ['E', 'W']
                for lane in intersection.lanes[side]
                for vehicle in lane.vehicles
                if self.is_vehicle_approaching_junction(vehicle, next_junction.id)
            )

            ew_count = sum(len(lane.vehicles) for side in ['E', 'W']
                          for lane in intersection.lanes[side])
            ns_count = sum(len(lane.vehicles) for side in ['N', 'S']
                          for lane in intersection.lanes[side])

            # Calculate expected green times
            ew_green_time = intersection.lights['E'].calculate_green_time(ew_count, approaching_count)
            ns_green_time = intersection.lights['N'].calculate_green_time(ns_count)

            # Add rows for each direction
            table_html += f"""
            <tr style='background-color: {'#3d3d3d' if i % 2 == 0 else '#333333'}'>
                <td style='border: 1px solid #ddd; padding: 8px;' rowspan='2'>Junction {i}</td>
                <td style='border: 1px solid #ddd; padding: 8px;'>East-West</td>
                <td style='border: 1px solid #ddd; padding: 8px;'>{ew_count} (+{approaching_count} approaching)</td>
                <td style='border: 1px solid #ddd; padding: 8px;'>{ew_green_time:.1f}s</td>
                <td style='border: 1px solid #ddd; padding: 8px;'>{intersection.lights['E'].state.upper()}</td>
            </tr>
            <tr style='background-color: {'#3d3d3d' if i % 2 == 0 else '#333333'}'>
                <td style='border: 1px solid #ddd; padding: 8px;'>North-South</td>
                <td style='border: 1px solid #ddd; padding: 8px;'>{ns_count}</td>
                <td style='border: 1px solid #ddd; padding: 8px;'>{ns_green_time:.1f}s</td>
                <td style='border: 1px solid #ddd; padding: 8px;'>{intersection.lights['N'].state.upper()}</td>
            </tr>
            """

        # Add timing rules explanation
        explanation = """
        </table>
        <br><br>
        <b>Timing Rules:</b><br>
        • Minimum green time: 10 seconds<br>
        • Maximum green time: 45 seconds<br>
        • Yellow time: 3 seconds<br>
        • Base timing: 3 seconds per vehicle<br>
        • Additional time for approaching vehicles: 2 seconds per vehicle<br>
        <br>
        <b>Coordination Rules:</b><br>
        • E/W traffic is synchronized between junctions<br>
        • N/S traffic operates independently at each junction<br>
        • Green time adapts based on vehicle density<br>
        </body>
        """

        table_html += explanation

        # Create text box with timing information
        pygame_gui.elements.UITextBox(
            html_text=table_html,
            relative_rect=pygame.Rect((10, 10), (580, 440)),
            manager=self.manager,
            container=self.timing_window
        )
    def reset_simulation(self):
        # Close timing window if open
        if self.timing_window:
            self.timing_window.kill()
            self.timing_window = None
            
        # Reset simulation state
        self.simulation_started = False
        self.start_button.set_text('Start')
        
        # Create new intersections
        self.setup_intersections()
        
        # Reset status label
        self.status_label.set_text("Select junction, side, lane and vehicle")
        
        # Reset dropdown selections
        self.junction_dropdown.selected_option = 'Junction 0'
        self.side_dropdown.selected_option = 'North'
        self.lane_dropdown.selected_option = 'Lane 1'
        self.vehicle_dropdown.selected_option = list(VEHICLE_TYPES.keys())[0]
    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.add_vehicle_button:
                self.add_vehicle()
            elif event.ui_element == self.start_button:
                if not self.simulation_started:
                    self.simulation_started = True
                    self.initialize_traffic_cycle()
                    self.start_button.set_text('Stop')
                else:
                    self.simulation_started = False
                    self.start_button.set_text('Start')
            elif event.ui_element == self.check_button:
                self.show_timing_info()
            elif event.ui_element == self.reset_button:
                self.reset_simulation()
    def add_vehicle(self):
        # Get selected values
        junction_tuple = self.junction_dropdown.selected_option
        side_tuple = self.side_dropdown.selected_option
        lane_tuple = self.lane_dropdown.selected_option
        vehicle_tuple = self.vehicle_dropdown.selected_option

        try:
            junction_str = junction_tuple[0] if isinstance(junction_tuple, tuple) else junction_tuple
            junction_idx = int(junction_str.split(' ')[-1])
            
            side_str = side_tuple[0] if isinstance(side_tuple, tuple) else side_tuple
            side = side_str[0].upper()
            
            lane_str = lane_tuple[0] if isinstance(lane_tuple, tuple) else lane_tuple
            lane_idx = int(lane_str.split(' ')[-1]) - 1
            
            vehicle_type = vehicle_tuple[0] if isinstance(vehicle_tuple, tuple) else vehicle_tuple
            
            junction = self.intersections[junction_idx]
            lane = junction.lanes[side][lane_idx]
            
            # Check if the lane allows placement
            if side == 'E' and lane_idx != 1:
                self.status_label.set_text("For East side, please select Lane 2")
                return
            elif side == 'W' and lane_idx != 0:
                self.status_label.set_text("For West side, please select Lane 1")
                return
                
            success = lane.place_vehicle(vehicle_type)
            if success:
                vehicle_count = len(lane.vehicles)
                self.status_label.set_text(
                    f"Added {vehicle_type} to Junction {junction_idx} {side} Lane {lane_idx+1} "
                    f"(Vehicles in lane: {vehicle_count})"
                )
            else:
                self.status_label.set_text("Failed to place vehicle - Invalid lane configuration")
                
        except Exception as e:
            print(f"Error adding vehicle: {e}")
            self.status_label.set_text("Error adding vehicle")

    def initialize_traffic_cycle(self):
        for intersection in self.intersections:
            for side in ['N', 'S', 'E', 'W']:
                intersection.lights[side].state = 'red'
                intersection.lights[side].timer = 0
                intersection.lights[side].countdown_active = False

    def is_vehicle_approaching_junction(self, vehicle, junction_id):
        """Check if a vehicle is approaching the specified junction."""
        junction_x = WINDOW_WIDTH//3 if junction_id == 0 else 2*WINDOW_WIDTH//3
        junction_y = WINDOW_HEIGHT//2
        vehicle_x, vehicle_y = vehicle.position
        
        # Define an approach distance
        approach_distance = 200
        
        if vehicle.direction == 'E':
            return 0 < (junction_x - vehicle_x) < approach_distance
        elif vehicle.direction == 'W':
            return 0 < (vehicle_x - junction_x) < approach_distance
        elif vehicle.direction == 'S':
            return 0 < (junction_y - vehicle_y) < approach_distance
        elif vehicle.direction == 'N':
            return 0 < (vehicle_y - junction_y) < approach_distance
        return False
        
        
    def update(self):
        if not self.simulation_started:
            return

        dt = 1/60

        # First calculate total E/W traffic density across both junctions
        total_ew_density = {
            'junction0': {
                'count': sum(len(lane.vehicles) for side in ['E', 'W']
                           for lane in self.intersections[0].lanes[side]),
                'approaching': 0
            },
            'junction1': {
                'count': sum(len(lane.vehicles) for side in ['E', 'W']
                           for lane in self.intersections[1].lanes[side]),
                'approaching': 0
            }
        }

        # Count vehicles approaching each junction
        for i, intersection in enumerate(self.intersections):
            next_junction = self.intersections[1 if i == 0 else 0]
            
            # Count vehicles moving towards next junction
            approaching_count = sum(
                1 for side in ['E', 'W']
                for lane in intersection.lanes[side]
                for vehicle in lane.vehicles
                if self.is_vehicle_approaching_junction(vehicle, next_junction.id)
            )
            
            next_junction_key = f'junction{next_junction.id}'
            total_ew_density[next_junction_key]['approaching'] = approaching_count

        # Now update each intersection
        for intersection in self.intersections:
            # Calculate local densities for this junction
            local_densities = {
                'NS': sum(len(lane.vehicles) for side in ['N', 'S']
                         for lane in intersection.lanes[side])
            }

            junction_key = f'junction{intersection.id}'
            ew_total = (total_ew_density[junction_key]['count'] +
                       total_ew_density[junction_key]['approaching'])

            # Determine if E/W needs to be synchronized
            needs_ew_sync = ew_total > 0

            if needs_ew_sync:
                # Calculate green time based on local density
                self.coordinate_ew_lights(intersection, ew_total)
                
                # NS traffic gets red during E/W coordination
                self.set_lights_for_axis(intersection, 'NS', 'red')
            else:
                # No E/W traffic, handle NS traffic independently
                if local_densities['NS'] > 0:
                    self.set_lights_for_axis(intersection, 'NS', 'green')
                    light = intersection.lights['N']  # Use North light for timing
                    if not light.countdown_active:
                        light.start_cycle(local_densities['NS'])
                    self.set_lights_for_axis(intersection, 'EW', 'red')
                else:
                    # No traffic in any direction
                    self.set_lights_for_axis(intersection, 'NS', 'red')
                    self.set_lights_for_axis(intersection, 'EW', 'red')

            # Update all lanes
            for side in ['E', 'W', 'N', 'S']:
                light_state = intersection.lights[side].state
                for lane in intersection.lanes[side]:
                    lane.update(dt, light_state)
    def coordinate_ew_lights(self, intersection, vehicle_count):
        """Coordinate E/W lights based on vehicle density and junction coordination rules"""
        lights = intersection.lights
        
        # Get vehicle counts for both junctions
        junction1_count = sum(len(lane.vehicles) for side in ['E', 'W']
                             for lane in self.intersections[1].lanes[side])
        
        # For Junction 0, set state based on Junction 1's vehicle count
        if intersection.id == 0:
            if junction1_count > 3:  # If Junction 1 has more than 3 vehicles
                for side in ['E', 'W']:
                    lights[side].state = 'red'
                    lights[side].countdown_active = False
                    lights[side].timer = 0
            else:  # If Junction 1 has 3 or fewer vehicles
                for side in ['E', 'W']:
                    lights[side].state = 'green'
                    if not lights[side].countdown_active:
                        lights[side].start_cycle(vehicle_count)
        
        # For Junction 1, proceed with normal operation
        elif intersection.id == 1:
            # If lights are already green and counting down, let them continue
            if lights['E'].state == 'green' and lights['E'].countdown_active:
                return
                
            # Start new green cycle for E/W
            for side in ['E', 'W']:
                lights[side].state = 'green'
                if not lights[side].countdown_active:
                    lights[side].start_cycle(vehicle_count)

    def calculate_densities(self, intersection):
        """Calculate vehicle densities for each direction"""
        return {
            'EW': {
                'count': sum(len(lane.vehicles) for side in ['E', 'W']
                           for lane in intersection.lanes[side]),
                'lanes': intersection.lanes['E'] + intersection.lanes['W']
            },
            'NS': {
                'count': sum(len(lane.vehicles) for side in ['N', 'S']
                           for lane in intersection.lanes[side]),
                'lanes': intersection.lanes['N'] + intersection.lanes['S']
            }
        }

    def count_approaching_vehicles(self, intersection):
        """Count vehicles approaching from adjacent intersection"""
        next_junction_id = 1 if intersection.id == 0 else 0
        return {
            'EW': sum(
                1 for side in ['E', 'W']
                for lane in self.intersections[next_junction_id].lanes[side]
                for vehicle in lane.vehicles
                if self.is_vehicle_approaching_junction(vehicle, intersection.id)
            ),
            'NS': 0  # N/S traffic doesn't move between junctions
        }

    def determine_priority(self, densities, approaching):
        """Determine which axis should have priority based on density"""
        ew_score = densities['EW']['count'] + approaching['EW'] * 0.5
        ns_score = densities['NS']['count']
        
        if ew_score > ns_score * 1.2:  # 20% threshold for switching
            return 'EW'
        elif ns_score > ew_score * 1.2:
            return 'NS'
        return None  # Keep current state if difference is small

    def update_intersection_lights(self, intersection, densities,
                                approaching, priority_axis, dt):
        """Update traffic lights based on density and priority"""
        for axis in ['EW', 'NS']:
            lights = ['E', 'W'] if axis == 'EW' else ['N', 'S']
            vehicle_count = densities[axis]['count']
            approaching_count = approaching[axis]
            
            # Check if any light in this axis is currently green
            current_green = any(intersection.lights[side].state == 'green'
                              for side in lights)
            
            if priority_axis == axis and not current_green:
                # Start new green cycle
                for side in lights:
                    light = intersection.lights[side]
                    light.state = 'green'
                    light.start_cycle(vehicle_count, approaching_count)
            
            # Update each light
            for side in lights:
                light = intersection.lights[side]
                current_count = sum(len(lane.vehicles)
                                  for lane in intersection.lanes[side])
                light.update(dt, vehicle_count > 0, current_count)

    def update_vehicles(self, intersection, dt):
        """Update vehicle movements based on light states"""
        for side in ['E', 'W', 'N', 'S']:
            light_state = intersection.lights[side].state
            for lane in intersection.lanes[side]:
                lane.update(dt, light_state)
    def set_lights_for_axis(self, intersection, axis, state):
        """Set lights for a given axis (EW or NS)"""
        if axis == 'EW':
            intersection.lights['E'].state = state
            intersection.lights['W'].state = state
        else:  # NS
            intersection.lights['N'].state = state
            intersection.lights['S'].state = state

        # Start countdown if turning green
        if state == 'green':
            if axis == 'EW':
                ew_count = sum(len(lane.vehicles) for side in ['E', 'W']
                             for lane in intersection.lanes[side])
                for side in ['E', 'W']:
                    if not intersection.lights[side].countdown_active:
                        intersection.lights[side].start_cycle(ew_count)
            else:
                ns_count = sum(len(lane.vehicles) for side in ['N', 'S']
                             for lane in intersection.lanes[side])
                for side in ['N', 'S']:
                    if not intersection.lights[side].countdown_active:
                        intersection.lights[side].start_cycle(ns_count)
    def draw_labels(self, screen):
        # Draw junction labels
        for intersection in self.intersections:
            x, y = intersection.position
            
            # Junction number label
            junction_text = f"Junction {intersection.id}"
            text_surface = self.font.render(junction_text, True, (255, 255, 255))
            text_rect = text_surface.get_rect(center=(x, y))
            screen.blit(text_surface, text_rect)
            
            # Side labels
            sides = {
                'N': (x, y - INTERSECTION_SIZE//2 - 20, 'North'),
                'S': (x, y + INTERSECTION_SIZE//2 + 20, 'South'),
                'E': (x + INTERSECTION_SIZE//2 + 20, y, 'East'),
                'W': (x - INTERSECTION_SIZE//2 - 20, y, 'West')
            }
            
            for _, (label_x, label_y, side_name) in sides.items():
                text_surface = self.font.render(side_name, True, (255, 255, 255))
                text_rect = text_surface.get_rect(center=(label_x, label_y))
                screen.blit(text_surface, text_rect)
            
            # Lane labels
            lane_offsets = {
                'E': [(0, -LANE_WIDTH//2, 'Lane 1'), (0, LANE_WIDTH//2, 'Lane 2')],
                'W': [(0, -LANE_WIDTH//2, 'Lane 1'), (0, LANE_WIDTH//2, 'Lane 2')],
                'N': [(-LANE_WIDTH//2, 0, 'Lane 1'), (LANE_WIDTH//2, 0, 'Lane 2')],
                'S': [(-LANE_WIDTH//2, 0, 'Lane 1'), (LANE_WIDTH//2, 0, 'Lane 2')]
            }
            
            for side, offsets in lane_offsets.items():
                base_x = x + (INTERSECTION_SIZE//2 + 60) * (1 if side == 'E' else -1 if side == 'W' else 0)
                base_y = y + (INTERSECTION_SIZE//2 + 60) * (1 if side == 'S' else -1 if side == 'N' else 0)
                
                for offset_x, offset_y, lane_name in offsets:
                    if side in ['E', 'W']:
                        label_x = base_x
                        label_y = base_y + offset_y
                    else:
                        label_x = base_x + offset_x
                        label_y = base_y
                    
                    text_surface = self.font.render(lane_name, True, (255, 255, 0))
                    text_rect = text_surface.get_rect(center=(label_x, label_y))
                    screen.blit(text_surface, text_rect)

    def draw(self, screen):
        screen.fill((34, 139, 34))  # Green background
        
        # Draw roads
        for intersection in self.intersections:
            x, y = intersection.position
            
            # Horizontal road
            pygame.draw.rect(screen, (50, 50, 50),
                           (0, y - ROAD_WIDTH//2, WINDOW_WIDTH, ROAD_WIDTH))
            
            # Vertical road
            pygame.draw.rect(screen, (50, 50, 50),
                           (x - ROAD_WIDTH//2, 0, ROAD_WIDTH, WINDOW_HEIGHT))
            
            # Draw lane markings
            for offset in [-ROAD_WIDTH//4, 0, ROAD_WIDTH//4]:
                # Horizontal lane markings
                pygame.draw.line(screen, (255, 255, 0),
                               (0, y + offset),
                               (WINDOW_WIDTH, y + offset), 2)
                # Vertical lane markings
                pygame.draw.line(screen, (255, 255, 0),
                               (x + offset, 0),
                               (x + offset, WINDOW_HEIGHT), 2)
        
        # Draw intersections
        for intersection in self.intersections:
            intersection.draw(screen)
            
        # Draw all labels
        self.draw_labels(screen)

def main():
    pygame.init()
    pygame.display.set_caption("Enhanced Traffic Control")
    window_surface = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    manager = pygame_gui.UIManager((WINDOW_WIDTH, WINDOW_HEIGHT))
    clock = pygame.time.Clock()
    
    traffic_system = TrafficSystem(manager)
    
    running = True
    while running:
        time_delta = clock.tick(60)/1000.0
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            
            manager.process_events(event)
            traffic_system.handle_event(event)
        
        manager.update(time_delta)
        traffic_system.update()
        traffic_system.draw(window_surface)
        manager.draw_ui(window_surface)
        
        pygame.display.update()
    
    pygame.quit()

if __name__ == "__main__":
    main()
