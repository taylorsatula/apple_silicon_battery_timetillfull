#!/usr/bin/env python3
import subprocess
import re
from datetime import datetime
import os
import json

LOG_FILE = "battery_log.txt"

def get_battery_info():
	"""Get battery information using ioreg"""
	cmd = ["ioreg", "-r", "-c", "AppleSmartBattery", "-w0"]
	result = subprocess.run(cmd, capture_output=True, text=True)
	
	# Initialize variables
	raw_current = None
	raw_max = None
	voltage = None
	design_capacity = None
	cell_voltages = []
	is_charging = False
	external_connected = False
	instant_amperage = None
	
	for line in result.stdout.split('\n'):
		line = line.strip()
		
		if '"AppleRawCurrentCapacity" = ' in line:
			match = re.search(r'= (\d+)', line)
			if match:
				raw_current = int(match.group(1))
				
		elif '"AppleRawMaxCapacity" = ' in line:
			match = re.search(r'= (\d+)', line)
			if match:
				raw_max = int(match.group(1))
				
		elif '"Voltage" = ' in line and not 'ShutDown' in line:
			match = re.search(r'= (\d+)', line)
			if match:
				voltage = int(match.group(1))
				
		elif '"DesignCapacity" = ' in line:
			match = re.search(r'= (\d+)', line)
			if match:
				design_capacity = int(match.group(1))
				
		elif '"CellVoltage" = ' in line:
			match = re.search(r'\(([\d,\s]+)\)', line)
			if match:
				values = match.group(1).split(',')
				cell_voltages = [int(v.strip()) for v in values]
				
		elif '"IsCharging" = ' in line:
			is_charging = 'Yes' in line
			
		elif '"ExternalConnected" = ' in line:
			external_connected = 'Yes' in line
			
		elif '"InstantAmperage" = ' in line:
			match = re.search(r'= (-?\d+)', line)
			if match:
				amp_raw = int(match.group(1))
				# Handle Apple's amperage format (negative values for discharge)
				if amp_raw > 2**31:
					instant_amperage = -((2**32) - amp_raw)
				else:
					instant_amperage = amp_raw

	return {
		'raw_current': raw_current,
		'raw_max': raw_max,
		'voltage': voltage,
		'design_capacity': design_capacity,
		'cell_voltages': cell_voltages,
		'is_charging': is_charging,
		'external_connected': external_connected,
		'instant_amperage': instant_amperage
	}

def load_log():
	"""Load the previous log entry"""
	if not os.path.exists(LOG_FILE):
		return None
	try:
		with open(LOG_FILE, 'r') as f:
			data = json.loads(f.read())
			# Validate log data
			if not all(k in data for k in ['timestamp', 'capacity', 'voltage']):
				return None
			return data
	except:
		return None

def save_log(data):
	"""Save current battery data to log"""
	log_entry = {
		'timestamp': datetime.now().isoformat(),
		'capacity': data['raw_current'],
		'voltage': data['voltage'],
		'external_connected': data['external_connected']
	}
	try:
		with open(LOG_FILE, 'w') as f:
			f.write(json.dumps(log_entry))
	except:
		pass

def calculate_rate(current_data, previous_data):
	"""Calculate rate of change in mAh/hour"""
	if not previous_data:
		return None
		
	current_time = datetime.now()
	previous_time = datetime.fromisoformat(previous_data['timestamp'])
	time_diff = (current_time - previous_time).total_seconds() / 3600  # in hours
	
	if time_diff < 0.0167:  # Minimum 1 minute between readings
		return None
		
	capacity_diff = current_data['raw_current'] - previous_data['capacity']
	if capacity_diff == 0:
		return None
		
	rate = abs(capacity_diff / time_diff)
	return rate if rate < 10000 else None  # Sanity check for unrealistic rates

def estimate_time_remaining(current_data, rate):
	"""Calculate time remaining based on current capacity and rate"""
	if not rate:
		return None
		
	if current_data['is_charging']:
		remaining_capacity = current_data['raw_max'] - current_data['raw_current']
	else:
		remaining_capacity = current_data['raw_current']
		
	hours_remaining = remaining_capacity / rate
	if hours_remaining > 24:  # Sanity check
		return None
		
	minutes_remaining = int((hours_remaining % 1) * 60)
	hours_remaining = int(hours_remaining)
	
	return f"{hours_remaining}h{minutes_remaining:02d}m"

def main():
	data = get_battery_info()
	if not all([data['raw_current'], data['raw_max'], data['voltage']]):
		print("Error: Could not get complete battery information")
		return
	
	previous_data = load_log()
	precise_percentage = (data['raw_current'] / data['raw_max']) * 100
	
	print("\nPrecise Battery Information:")
	print(f"Raw Current Capacity: {data['raw_current']} mAh")
	print(f"Raw Maximum Capacity: {data['raw_max']} mAh")
	print(f"Precise Charge Level: {precise_percentage:.4f}%")
	print(f"Battery Voltage: {data['voltage']/1000:.3f}V")
	
	if data['design_capacity']:
		health = (data['raw_max'] / data['design_capacity']) * 100
		print(f"Design Capacity: {data['design_capacity']} mAh")
		print(f"Battery Health: {health:.2f}%")
	
	if data['cell_voltages']:
		print("\nIndividual Cell Voltages:")
		for i, v in enumerate(data['cell_voltages'], 1):
			print(f"Cell {i}: {v/1000:.3f}V")
	
	print(f"\nPower Status: {'Connected to Power' if data['external_connected'] else 'On Battery'}")
	print(f"Battery Status: {'Charging' if data['is_charging'] else 'Not Charging'}")
	
	# Calculate rate and time remaining
	rate = calculate_rate(data, previous_data)
	if rate:
		if data['is_charging']:
			print(f"Charging Rate: {rate:.1f} mAh/hour")
			time_remaining = estimate_time_remaining(data, rate)
			if time_remaining:
				print(f"Estimated Time to Full: {time_remaining}")
		else:
			print(f"Discharge Rate: {rate:.1f} mAh/hour")
			time_remaining = estimate_time_remaining(data, rate)
			if time_remaining:
				print(f"Estimated Time to Empty: {time_remaining}")
	
	# Only save log if values are reasonable
	save_log(data)

if __name__ == "__main__":
	main()