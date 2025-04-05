import pygame_gui
import numpy as np
import random
from collections import defaultdict
import pygame

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

class Accident:
    def __init__(self, position, side, lane_number):
        self.position = position
        self.side = side
        self.lane_number = lane_number
        self.size = 50  # Size of accident area
        self.active = True
        # Remove automatic clearing since user will manually clear accidents
        self.flash_timer = 0
        self.flash_interval = 0.5
        self.show_warning = True
        
    def update(self, dt):
        # Update flash effect timer only
        self.flash_timer += dt
        if self.flash_timer >= self.flash_interval:
            self.show_warning = not self.show_warning
            self.flash_timer = 0
                
    def draw(self, screen):
        if not self.active:
            return
            
        # Draw accident area with flashing warning
        if self.show_warning:
            color = (255, 165, 0)  # Orange when visible
        else:
            color = (255, 0, 0)  # Red when flashing
            
        # Draw accident area based on side
        x, y = self.position
        if self.side in ['E', 'W']:
            # Horizontal accident
            pygame.draw.rect(screen, color,
                           (x - self.size//2, y - LANE_WIDTH//2,
                            self.size, LANE_WIDTH))
        else:
            # Vertical accident
            pygame.draw.rect(screen, color,
                           (x - LANE_WIDTH//2, y - self.size//2,
                            LANE_WIDTH, self.size))
            
        # Draw "ACCIDENT" text instead of timer
        font = pygame.font.Font(None, 20)
        time_text = font.render("ACCIDENT", True, (0, 0, 0))
        text_rect = time_text.get_rect(center=(x, y))
        screen.blit(time_text, text_rect)
        
class Lane:
    def __init__(self, junction_id, side, lane_number, position):
        self.junction_id = junction_id
        self.side = side
        self.lane_number = lane_number
        self.position = position
        self.vehicles = []
        self.spacing = 5
        self.accident = None
        self.flow_rate_factor = 1.0  # Normal flow rate
        
        # Determine direction based on side and lane number
        if side == 'E':
            self.direction = 'W'  # East side, vehicles move westward
            self.spawn_point = [WINDOW_WIDTH - 100, position[1]]
        elif side == 'W':
            self.direction = 'E'  # West side, vehicles move eastward
            self.spawn_point = [100, position[1]]
        elif side == 'N':
            self.direction = 'S'  # North side, vehicles move southward
            self.spawn_point = [position[0], 100]
        elif side == 'S':
            self.direction = 'N'  # South side, vehicles move northward
            self.spawn_point = [position[0], WINDOW_HEIGHT - 100]
            
    def place_vehicle(self, vehicle_type):
        # Lane 1 (index 0) only accepts vehicles from North/West
        # Lane 2 (index 1) only accepts vehicles from South/East
        allowed = (
            (self.lane_number == 0 and self.side in ['W', 'N']) or
            (self.lane_number == 1 and self.side in ['E', 'S'])
        )
        
        if not allowed:
            return False
            
        vehicle_length = VEHICLE_TYPES[vehicle_type]['length']
        base_position = list(self.spawn_point)
        
        # Calculate offset based on existing vehicles
        total_offset = sum([VEHICLE_TYPES[v.type]['length'] + self.spacing for v in self.vehicles])
        
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
    
    def place_accident(self, position=None):
        if self.accident and self.accident.active:
            return False  # Already has an active accident
            
        # If position not provided, calculate a default position
        if position is None:
            if self.direction in ['E', 'W']:
                # For horizontal lanes, place accident in the middle of the lane
                x = self.position[0] + (100 if self.direction == 'E' else -100)
                y = self.position[1]
            else:
                # For vertical lanes, place accident in the middle of the lane
                x = self.position[0]
                y = self.position[1] + (100 if self.direction == 'S' else -100)
            position = (x, y)
            
        self.accident = Accident(position, self.side, self.lane_number)
        # Reduce flow rate when accident occurs
        self.flow_rate_factor = 0.0  # Stop traffic in this lane only
        return True
    
    def clear_accident(self):
        if self.accident and self.accident.active:
            self.accident.active = False
            self.flow_rate_factor = 1.0  # Restore normal flow
            # Note: The traffic light will be updated in the next cycle of determine_traffic_flow_priorities
            return True
        return False
        
    def update(self, dt, traffic_light_state):
        # Update accident if present
        if self.accident and self.accident.active:
            self.accident.update(dt)
            
        for i, vehicle in enumerate(self.vehicles):
            # Check if there's a vehicle ahead
            min_distance = VEHICLE_TYPES[vehicle.type]['length'] + self.spacing
            can_move_forward = True
            
            # Check for accident in path - ONLY if the accident is ahead of the vehicle in its direction of travel
            if self.accident and self.accident.active:
                # Calculate distance to accident - only consider accidents that are in front of the vehicle
                if self.direction == 'E' and vehicle.position[0] < self.accident.position[0]:
                    # Vehicle moving east, accident is ahead (to the right)
                    accident_distance = self.accident.position[0] - vehicle.position[0]
                    if accident_distance < min_distance + self.accident.size//2:
                        can_move_forward = False
                elif self.direction == 'W' and vehicle.position[0] > self.accident.position[0]:
                    # Vehicle moving west, accident is ahead (to the left)
                    accident_distance = vehicle.position[0] - self.accident.position[0]
                    if accident_distance < min_distance + self.accident.size//2:
                        can_move_forward = False
                elif self.direction == 'S' and vehicle.position[1] < self.accident.position[1]:
                    # Vehicle moving south, accident is ahead (below)
                    accident_distance = self.accident.position[1] - vehicle.position[1]
                    if accident_distance < min_distance + self.accident.size//2:
                        can_move_forward = False
                elif self.direction == 'N' and vehicle.position[1] > self.accident.position[1]:
                    # Vehicle moving north, accident is ahead (above)
                    accident_distance = vehicle.position[1] - self.accident.position[1]
                    if accident_distance < min_distance + self.accident.size//2:
                        can_move_forward = False
            
            # Check for vehicle ahead
            if i > 0:  # If not the first vehicle
                vehicle_ahead = self.vehicles[i-1]
                if self.direction == 'E':
                    distance = vehicle_ahead.position[0] - vehicle.position[0]
                elif self.direction == 'W':
                    distance = vehicle.position[0] - vehicle_ahead.position[0]
                elif self.direction == 'S':
                    distance = vehicle_ahead.position[1] - vehicle.position[1]
                elif self.direction == 'N':
                    distance = vehicle.position[1] - vehicle_ahead.position[1]
                
                if abs(distance) < min_distance:
                    can_move_forward = False
            
            # Only move if light is green, there's no accident in the lane
            # or if there is an accident, the vehicle can move (not blocked by accident)
            should_move = traffic_light_state == 'green' and can_move_forward
            
            # If there's an active accident in this lane, the flow rate is already set to 0
            # so vehicles won't move even if should_move is true
            effective_speed = VEHICLE_TYPES[vehicle.type]['speed']
            if self.accident and self.accident.active:
                effective_speed *= self.flow_rate_factor
            vehicle.update(dt, should_move, effective_speed)
            
        # Remove vehicles that have moved off screen
        self.vehicles = [v for v in self.vehicles if not v.is_off_screen()]
    


    def draw(self, screen):
        # Draw all vehicles in the lane
        for vehicle in self.vehicles:
            vehicle.draw(screen)
            
        # Draw accident if active
        if self.accident and self.accident.active:
            self.accident.draw(screen)

    def has_active_accident(self):
        return self.accident is not None and self.accident.active

class TrafficLight:
    def __init__(self, position, direction, junction_id):
        self.position = position
        self.direction = direction
        self.junction_id = junction_id
        self.state = 'red'
        self.timer = 0
        self.cycle_time = 0
        self.countdown_active = False
        
    def start_countdown(self, cycle_time):
        self.cycle_time = cycle_time
        self.timer = cycle_time
        self.countdown_active = True
    
    def update(self, dt, vehicles_present=False, has_accident=False):
        # Don't change state if there's an accident on this direction
        if has_accident and self.state == 'green':
            self.state = 'red'
            self.timer = 0
            self.countdown_active = False
            return
            
        if not vehicles_present and self.state != 'red':
            self.state = 'red'
            self.timer = 0
            self.countdown_active = False
            return

        if self.timer > 0 and self.countdown_active:
            self.timer -= dt
            
            if self.timer <= 0:
                if self.state == 'green':
                    self.state = 'yellow'
                    self.timer = YELLOW_TIME
                elif self.state == 'yellow':
                    self.state = 'red'
                    self.timer = 0
            
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
        # Track which direction currently has green light
        self.current_green_direction = None
        
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
                
                # Update current green direction
                if state == 'green':
                    if side in ['N', 'S']:
                        self.current_green_direction = 'NS'
                    else:  # side in ['E', 'W']
                        self.current_green_direction = 'EW'

    def check_for_accidents(self):
        accidents = {}
        for side, lanes in self.lanes.items():
            accidents[side] = any(lane.has_active_accident() for lane in lanes)
        return accidents
    
    def count_vehicles(self):
        vehicle_counts = {}
        for side, lanes in self.lanes.items():
            vehicle_counts[side] = sum(len(lane.vehicles) for lane in lanes)
        return vehicle_counts
        
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
        for side, side_lanes in self.lanes.items():
            for lane in side_lanes:
                # Draw lane marker
                pygame.draw.circle(screen, (255, 255, 255),
                                 (int(lane.position[0]), int(lane.position[1])), 3)
                # Draw lane contents (vehicles and accidents)
                lane.draw(screen)

class Vehicle:
    def __init__(self, position, direction, vehicle_type='Car'):
        self.position = list(position)
        self.direction = direction
        self.type = vehicle_type
        self.properties = VEHICLE_TYPES[self.type]
        self.speed = self.properties['speed']
        self.color = self.properties['color']
        self.stopped = False
        self.label = ""  # Will be set by Lane class
        
    def update(self, dt, can_move, flow_rate_factor=1.0):
        if not can_move:
            return
            
        effective_speed = self.speed * flow_rate_factor
        
        if self.direction == 'E':
            self.position[0] += effective_speed
        elif self.direction == 'W':
            self.position[0] -= effective_speed
        elif self.direction == 'S':
            self.position[1] += effective_speed
        elif self.direction == 'N':
            self.position[1] -= effective_speed
            
    def is_off_screen(self):
        return (self.direction == 'E' and self.position[0] > WINDOW_WIDTH + 100) or \
               (self.direction == 'W' and self.position[0] < -100) or \
               (self.direction == 'S' and self.position[1] > WINDOW_HEIGHT + 100) or \
               (self.direction == 'N' and self.position[1] < -100)
        
    def draw(self, screen):
        x, y = self.position
        length = self.properties['length']
        width = self.properties['width']
        
        # Draw vehicle
        if self.direction in ['E', 'W']:
            rect = pygame.Rect(x - length//2, y - width//2, length, width)
        else:  # N or S direction
            rect = pygame.Rect(x - width//2, y - length//2, width, length)
        pygame.draw.rect(screen, self.color, rect)
        
        # Draw label above vehicle (optional, for debugging)
        font = pygame.font.Font(None, 20)
        text = font.render(self.label, True, (255, 255, 255))
        text_rect = text.get_rect(center=(x, y - width - 10))
        screen.blit(text, text_rect)


class TrafficSystem:
    def __init__(self, manager):
        self.manager = manager
        # Create a single intersection at the center of the screen
        self.intersection = Intersection((WINDOW_WIDTH//2, WINDOW_HEIGHT//2), 0)
        self.setup_gui()
        self.simulation_started = False
        self.font = pygame.font.Font(None, 24)  # Font for labels
        self.placing_accident = False
        self.clearing_accident = False
        self.accident_side = None
        self.accident_lane = None
        self.cycle_timer = 0
        
    def setup_gui(self):
        # Side selection
        directions = ['North', 'South', 'East', 'West']
        self.side_dropdown = pygame_gui.elements.UIDropDownMenu(
            options_list=directions,
            starting_option=directions[0],
            relative_rect=pygame.Rect((20, 20), (120, 30)),
            manager=self.manager
        )
        
        # Lane selection
        lanes = ['Lane 1', 'Lane 2']
        self.lane_dropdown = pygame_gui.elements.UIDropDownMenu(
            options_list=lanes,
            starting_option=lanes[0],
            relative_rect=pygame.Rect((150, 20), (100, 30)),
            manager=self.manager
        )
        
        # Vehicle type selection
        vehicle_types = list(VEHICLE_TYPES.keys())
        self.vehicle_dropdown = pygame_gui.elements.UIDropDownMenu(
            options_list=vehicle_types,
            starting_option=vehicle_types[0],
            relative_rect=pygame.Rect((260, 20), (120, 30)),
            manager=self.manager
        )
        
        # Add vehicle button
        self.add_vehicle_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect((390, 20), (100, 30)),
            text='Add Vehicle',
            manager=self.manager
        )
        
        # Start button
        self.start_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect((500, 20), (100, 30)),
            text='Start',
            manager=self.manager
        )
        
        # Add accident button
        self.add_accident_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect((610, 20), (120, 30)),
            text='Add Accident',
            manager=self.manager
        )
        
        # Clear accident button
        self.clear_accident_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect((740, 20), (120, 30)),
            text='Clear Accident',
            manager=self.manager
        )
        
        # Status label
        self.status_label = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect((870, 20), (140, 30)),
            text="Select side and lane",
            manager=self.manager
        )

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
            elif event.ui_element == self.add_accident_button:
                self.start_accident_placement()
            elif event.ui_element == self.clear_accident_button:
                self.start_accident_clearing()
        
        # Handle mouse click for accident placement
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.placing_accident:
                self.place_accident_at_mouse(event.pos)
            elif self.clearing_accident:
                self.clear_accident_at_mouse(event.pos)

    def start_accident_clearing(self):
        self.clearing_accident = True
        self.status_label.set_text("Click on an accident to clear it")
        
    def clear_accident_at_mouse(self, mouse_pos):
        if not self.clearing_accident:
            return
            
        # Find the accident closest to the mouse click
        closest_accident = None
        closest_dist = float('inf')
        
        for side, lanes in self.intersection.lanes.items():
            for lane in lanes:
                if lane.accident and lane.accident.active:
                    acc_x, acc_y = lane.accident.position
                    mouse_x, mouse_y = mouse_pos
                    dist = ((acc_x - mouse_x) ** 2 + (acc_y - mouse_y) ** 2) ** 0.5
                    
                    # If mouse is within 30 pixels of the accident center
                    if dist < 30 and dist < closest_dist:
                        closest_accident = (side, lane.lane_number, lane)
                        closest_dist = dist
        
        if closest_accident:
            side, lane_idx, lane = closest_accident
            lane.clear_accident()
            self.status_label.set_text(f"Cleared accident on {side} Lane {lane_idx+1}")
            
            # Recalculate traffic priorities after clearing an accident
            if self.simulation_started:
                self.determine_traffic_flow_priorities()
        else:
            self.status_label.set_text("No accident found at that location")
            
        self.clearing_accident = False

    def start_accident_placement(self):
        side_tuple = self.side_dropdown.selected_option
        lane_tuple = self.lane_dropdown.selected_option
        
        try:
            side_str = side_tuple[0] if isinstance(side_tuple, tuple) else side_tuple
            self.accident_side = side_str[0].upper()  # Convert to single letter format (E/W/N/S)
            
            lane_str = lane_tuple[0] if isinstance(lane_tuple, tuple) else lane_tuple
            self.accident_lane = int(lane_str.split(' ')[-1]) - 1
            
            self.placing_accident = True
            self.status_label.set_text("Click on the road to place accident")
        except Exception as e:
            print(f"Error starting accident placement: {e}")
            self.status_label.set_text("Error setting up accident placement")

    def place_accident_at_mouse(self, mouse_pos):
        if not self.placing_accident:
            return
            
        try:
            lane = self.intersection.lanes[self.accident_side][self.accident_lane]
            success = lane.place_accident(mouse_pos)
            
            if success:
                self.status_label.set_text(
                    f"Accident placed on {self.accident_side} Lane {self.accident_lane+1}"
                )
                
                # Recalculate traffic priorities after placing an accident
                if self.simulation_started:
                    self.determine_traffic_flow_priorities()
            else:
                self.status_label.set_text("Failed to place accident - Already has active accident")
        except Exception as e:
            print(f"Error placing accident: {e}")
            self.status_label.set_text("Error placing accident")
            
        self.placing_accident = False

    def add_vehicle(self):
        # Get selected values
        side_tuple = self.side_dropdown.selected_option
        lane_tuple = self.lane_dropdown.selected_option
        vehicle_tuple = self.vehicle_dropdown.selected_option

        try:
            side_str = side_tuple[0] if isinstance(side_tuple, tuple) else side_tuple
            side = side_str[0].upper()  # Convert to single letter format (E/W/N/S)
            
            lane_str = lane_tuple[0] if isinstance(lane_tuple, tuple) else lane_tuple
            lane_idx = int(lane_str.split(' ')[-1]) - 1
            
            vehicle_type = vehicle_tuple[0] if isinstance(vehicle_tuple, tuple) else vehicle_tuple
            
            lane = self.intersection.lanes[side][lane_idx]
            
            # Check lane restrictions based on side
            if side == 'E' and lane_idx != 1:
                self.status_label.set_text("For East side, please select Lane 2")
                return
            elif side == 'W' and lane_idx != 0:
                self.status_label.set_text("For West side, please select Lane 1")
                return
            elif side == 'N' and lane_idx != 0:
                self.status_label.set_text("For North side, please select Lane 1")
                return
            elif side == 'S' and lane_idx != 1:
                self.status_label.set_text("For South side, please select Lane 2")
                return
                
            success = lane.place_vehicle(vehicle_type)
            if success:
                vehicle_count = len(lane.vehicles)
                self.status_label.set_text(
                    f"Added {vehicle_type} to {side_str} Lane {lane_idx+1} "
                    f"(Vehicles in lane: {vehicle_count})"
                )
                
                # If simulation is running, update priorities
                if self.simulation_started:
                    self.determine_traffic_flow_priorities()
            else:
                self.status_label.set_text("Failed to place vehicle - Invalid lane configuration")
                
        except Exception as e:
            print(f"Error adding vehicle: {e}")
            self.status_label.set_text("Error adding vehicle")

    def initialize_traffic_cycle(self):
        # Initially set all lights to red
        all_red_states = {side: 'red' for side in ['N', 'S', 'E', 'W']}
        self.intersection.update_lights(all_red_states)
        
        # Determine which directions should get green lights based on vehicle counts and accidents
        self.determine_traffic_flow_priorities()

    def calculate_densities(self):
        """Calculate the density of vehicles in each direction."""
        densities = {}
        total_vehicles = 0
        
        # Count vehicles in each direction
        for side in ['N', 'S', 'E', 'W']:
            vehicle_count = sum(len(lane.vehicles) for lane in self.intersection.lanes[side])
            densities[side] = vehicle_count
            total_vehicles += vehicle_count
        
        # Convert to density ratios if there are vehicles
        if total_vehicles > 0:
            for side in densities:
                densities[side] = densities[side] / total_vehicles
                
        return densities

    def determine_traffic_flow_priorities(self):
        # Check for accidents first
        accidents = self.intersection.check_for_accidents()
        
        # Calculate densities
        densities = self.calculate_densities()
        
        # Initialize all traffic lights to red by default
        new_states = {side: 'red' for side in ['N', 'S', 'E', 'W']}
        
        # Find the direction with highest density that doesn't have an accident
        max_density = 0
        best_direction = None
        
        for side in ['N', 'S', 'E', 'W']:
            if not accidents[side] and densities.get(side, 0) > max_density:
                max_density = densities[side]
                best_direction = side
        
        # If we found a suitable direction, give it green light
        if best_direction is not None:
            # Determine if this is a North-South or East-West direction
            if best_direction in ['N', 'S']:
                # Give green to both North and South if no accidents
                new_states['N'] = 'green' if not accidents['N'] else 'red'
                new_states['S'] = 'green' if not accidents['S'] else 'red'
                # Set green time based on density
                green_time = MIN_GREEN_TIME + (MAX_GREEN_TIME - MIN_GREEN_TIME) * densities[best_direction]
                self.intersection.set_timing(green_time)
            else:  # East or West
                # Give green to both East and West if no accidents
                new_states['E'] = 'green' if not accidents['E'] else 'red'
                new_states['W'] = 'green' if not accidents['W'] else 'red'
                # Set green time based on density
                green_time = MIN_GREEN_TIME + (MAX_GREEN_TIME - MIN_GREEN_TIME) * densities[best_direction]
                self.intersection.set_timing(green_time)
        
        # Update the traffic lights with the new states
        self.intersection.update_lights(new_states)
        
        # Debug information
        print("Traffic light states updated based on density and accidents:")
        for side in ['N', 'S', 'E', 'W']:
            accident_status = "ACCIDENT" if accidents[side] else "No accident"
            density = densities.get(side, 0)
            print(f"{side}: {new_states[side].upper()} - Density: {density:.2f}, {accident_status}")

    
    def update(self):
        if not self.simulation_started:
            return

        dt = 1/60  # Assuming 60 FPS
        
        # Determine traffic flow priorities (set lights based on accidents)
        self.determine_traffic_flow_priorities()
        
        # Update lanes and vehicles
        for side, lanes in self.intersection.lanes.items():
            for lane in lanes:
                # Pass the specific light state for this side
                light_state = self.intersection.lights[side].state
                lane.update(dt, light_state)
    def draw_labels(self, screen):
        # Draw junction label
        x, y = self.intersection.position
        
        # Junction label
        junction_text = "Traffic Junction"
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

    def draw(self, screen):
        screen.fill((34, 139, 34))  # Green background
        
        # Draw roads
        x, y = self.intersection.position
        
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
        
        # Draw intersection
        self.intersection.draw(screen)
            
        # Draw all labels
        self.draw_labels(screen)

def main():
    pygame.init()
    pygame.display.set_caption("Traffic Control Simulation")
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

