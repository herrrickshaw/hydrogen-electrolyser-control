"""
Practical Examples for Hydrogen Electrolyser Control System
Run these examples to test different electrolyser configurations and operations
"""

import time
import sys
from electrolyser_control_system import (
    ElectrolyserControlSystem,
    ElectrolyserType,
    OperatingMode
)
from electrolyser_advanced_control import (
    AdvancedElectrolyserController,
    RampProfile
)


# ==================== Example 1: Basic PEM Operation ====================

def example_basic_pem_operation():
    """
    Example 1: Basic PEM electrolyser operation
    - Start operation
    - Set voltage and power
    - Monitor status
    - Graceful shutdown
    """
    print("\n" + "="*70)
    print("EXAMPLE 1: Basic PEM Electrolyser Operation")
    print("="*70)

    system = ElectrolyserControlSystem(ElectrolyserType.PEM)

    # Start operation
    print("\n1. Starting electrolyser...")
    system.start_operation()
    time.sleep(1)

    # Set voltage
    print("2. Setting voltage to 45V...")
    system.set_voltage(45.0)
    time.sleep(0.5)

    # Set power
    print("3. Setting power to 3500W...")
    system.set_power(3500.0)
    time.sleep(0.5)

    # Transition to normal mode
    system.electrolyser.transition_mode(OperatingMode.NORMAL)

    # Simulate some operation
    print("4. Operating for 5 seconds...")
    for i in range(50):
        system.electrolyser.update_state(0.1)
        if i % 10 == 0:
            status = system.get_status()
            print(f"   t={i*0.1:.1f}s: V={status['voltage']:.1f}V, "
                  f"P={status['power']:.0f}W, H2={status['hydrogen_produced']:.4f}Nm³")
        time.sleep(0.01)

    # Print final status
    print("\n5. Final Status:")
    system.print_status()

    # Stop
    print("6. Stopping electrolyser...")
    system.stop_operation()

    print("✓ Example 1 complete\n")


# ==================== Example 2: Voltage Ramp-Up ====================

def example_voltage_ramp_up():
    """
    Example 2: Gradual voltage ramp-up
    - Start at 20V
    - Ramp to 50V over 10 seconds
    - Monitor efficiency change
    """
    print("\n" + "="*70)
    print("EXAMPLE 2: Voltage Ramp-Up with Efficiency Monitoring")
    print("="*70)

    system = ElectrolyserControlSystem(ElectrolyserType.AEM)

    print("\n1. Starting electrolyser...")
    system.start_operation()
    time.sleep(1)

    print("2. Ramping voltage from 25V to 50V over 10 seconds...")
    system.ramp_to_voltage(
        target_voltage=50.0,
        ramp_rate=2.5,  # 2.5 V/s
        dt=0.1
    )

    # Operate at full voltage
    print("3. Operating at maximum voltage for 5 seconds...")
    system.electrolyser.transition_mode(OperatingMode.NORMAL)
    system.set_power(4000.0)

    for i in range(50):
        system.electrolyser.update_state(0.1)
        if i % 10 == 0:
            status = system.get_status()
            print(f"   Efficiency: {status['efficiency']:.2f}%")
        time.sleep(0.01)

    print("\n4. Final Status:")
    system.print_status()

    print("5. Stopping...")
    system.stop_operation()

    print("✓ Example 2 complete\n")


# ==================== Example 3: Power Ramp-Up ====================

def example_power_ramp_up():
    """
    Example 3: Power ramp-up with production tracking
    - Ramp from 1000W to 4500W
    - Track hydrogen production
    - Monitor efficiency change
    """
    print("\n" + "="*70)
    print("EXAMPLE 3: Power Ramp-Up with Production Tracking")
    print("="*70)

    system = ElectrolyserControlSystem(ElectrolyserType.ALKALINE)

    print("\n1. Starting electrolyser...")
    system.start_operation()
    time.sleep(1)

    print("2. Ramping power from 1000W to 4500W over 20 seconds...")
    system.ramp_to_power(
        target_power=4500.0,
        ramp_rate=175.0,  # 175 W/s
        dt=0.1
    )

    print("\n3. Operating at maximum power for 5 seconds...")
    for i in range(50):
        system.electrolyser.update_state(0.1)
        if i % 10 == 0:
            status = system.get_status()
            h2_rate = status['hydrogen_produced'] / (status['run_time'] / 3600) if status['run_time'] > 0 else 0
            print(f"   H2: {status['hydrogen_produced']:.4f}Nm³, "
                  f"Rate: {h2_rate:.3f}Nm³/h, "
                  f"Efficiency: {status['efficiency']:.1f}%")
        time.sleep(0.01)

    print("\n4. Final Production Summary:")
    status = system.get_status()
    print(f"   Total H2 produced: {status['hydrogen_produced']:.4f} Nm³")
    print(f"   Total O2 produced: {status['oxygen_produced']:.4f} Nm³")
    print(f"   Water consumed: {status['water_consumed']:.4f} L")
    print(f"   Average efficiency: {status['efficiency']:.1f}%")
    print(f"   Total runtime: {status['run_time']:.1f} seconds")

    print("\n5. Stopping...")
    system.stop_operation()

    print("✓ Example 3 complete\n")


# ==================== Example 4: Advanced Scheduling ====================

def example_advanced_scheduling():
    """
    Example 4: Advanced scheduling with multiple ramp profiles
    - Linear voltage ramp
    - Exponential power ramp
    - Real-time data logging
    - Operation report generation
    """
    print("\n" + "="*70)
    print("EXAMPLE 4: Advanced Scheduling with Ramp Profiles")
    print("="*70)

    controller = AdvancedElectrolyserController(ElectrolyserType.PEM)

    print("\n1. Registering safety callback...")
    def on_safety_event(event_type: str, message: str):
        print(f"\n⚠️  SAFETY EVENT: {event_type} - {message}")

    controller.register_safety_callback(on_safety_event)

    print("2. Starting controller...")
    controller.start()

    print("3. Setting schedules:")
    print("   - Voltage: 30V → 48V (10s, LINEAR)")
    print("   - Power: 1000W → 4000W (15s, EXPONENTIAL)")

    controller.set_voltage_ramp(
        start_voltage=30.0,
        end_voltage=48.0,
        duration=10.0,
        profile=RampProfile.LINEAR
    )

    controller.set_power_ramp(
        start_power=1000.0,
        end_power=4000.0,
        duration=15.0,
        profile=RampProfile.EXPONENTIAL
    )

    print("\n4. Monitoring for 20 seconds...")
    for i in range(40):
        time.sleep(0.5)
        status = controller.get_real_time_status()
        if status and i % 4 == 0:
            print(f"   t={i*0.5:.1f}s: V={status['voltage']:.1f}V, "
                  f"P={status['power']:.0f}W, "
                  f"Eff={status['efficiency']:.1f}%")

    print("\n5. Stopping and generating report...")
    controller.stop()

    summary = controller.logger.get_summary()
    print("\n6. Operation Summary:")
    print(f"   Duration: {summary['duration_seconds']:.1f}s")
    print(f"   Voltage: {summary['voltage_avg']:.1f}V (min={summary['voltage_min']:.1f}, max={summary['voltage_max']:.1f})")
    print(f"   Power: {summary['power_avg']:.0f}W (min={summary['power_min']:.0f}, max={summary['power_max']:.0f})")
    print(f"   Efficiency: {summary['efficiency_avg']:.1f}%")
    print(f"   H2 produced: {summary['total_hydrogen']:.4f} Nm³")
    print(f"   Alerts: {summary['alerts']}, Warnings: {summary['warnings']}")

    print(f"\n   Logs saved to:")
    print(f"   - CSV: {controller.logger.csv_file}")
    print(f"   - JSON: {controller.logger.json_file}")

    print("✓ Example 4 complete\n")


# ==================== Example 5: Multi-Type Comparison ====================

def example_electrolyser_comparison():
    """
    Example 5: Compare different electrolyser types
    - Run same sequence on PEM, AEM, and Alkaline
    - Compare efficiency and production
    """
    print("\n" + "="*70)
    print("EXAMPLE 5: Electrolyser Type Comparison")
    print("="*70)

    types = [ElectrolyserType.PEM, ElectrolyserType.AEM, ElectrolyserType.ALKALINE]
    results = {}

    for etype in types:
        print(f"\n{'='*70}")
        print(f"Testing {etype.value} Electrolyser")
        print(f"{'='*70}")

        system = ElectrolyserControlSystem(etype)

        # Start
        system.start_operation()
        specs = system.electrolyser.specs

        print(f"\nSpecifications:")
        print(f"  Nominal Voltage: {specs.nominal_voltage}V")
        print(f"  Nominal Current: {specs.nominal_current}A")
        print(f"  Nominal Power: {specs.nominal_power}W")
        print(f"  Max Efficiency: {specs.max_efficiency}%")
        print(f"  H2 Rate: {specs.hydrogen_production_rate} Nm³/h")

        # Ramp to nominal conditions
        print(f"\nRamping to nominal power ({specs.nominal_power}W)...")
        system.set_voltage(specs.nominal_voltage)
        system.set_power(specs.nominal_power)
        system.electrolyser.transition_mode(OperatingMode.NORMAL)

        # Operate for 30 seconds
        print("Operating for 30 seconds...")
        for i in range(300):
            system.electrolyser.update_state(0.1)
            time.sleep(0.01)

        # Get results
        status = system.get_status()
        results[etype.value] = {
            "efficiency": status['efficiency'],
            "hydrogen": status['hydrogen_produced'],
            "oxygen": status['oxygen_produced'],
            "water": status['water_consumed'],
            "voltage": status['voltage'],
            "current": status['current']
        }

        print(f"\nResults:")
        print(f"  Final Efficiency: {status['efficiency']:.1f}%")
        print(f"  H2 Produced: {status['hydrogen_produced']:.4f} Nm³")
        print(f"  O2 Produced: {status['oxygen_produced']:.4f} Nm³")
        print(f"  Water Used: {status['water_consumed']:.4f} L")

        system.stop_operation()
        time.sleep(1)

    # Comparison
    print(f"\n{'='*70}")
    print("COMPARISON SUMMARY")
    print(f"{'='*70}")
    print(f"{'Type':<15} {'Efficiency':<15} {'H2 (Nm³)':<15} {'Water (L)':<15}")
    print("-" * 60)
    for etype, res in results.items():
        print(f"{etype:<15} {res['efficiency']:.1f}%{'':<10} "
              f"{res['hydrogen']:.4f}{'':<10} {res['water']:.4f}")

    best_eff = max(results.items(), key=lambda x: x[1]['efficiency'])
    best_h2 = max(results.items(), key=lambda x: x[1]['hydrogen'])

    print(f"\nBest Efficiency: {best_eff[0]} ({best_eff[1]['efficiency']:.1f}%)")
    print(f"Best H2 Production: {best_h2[0]} ({best_h2[1]['hydrogen']:.4f} Nm³)")

    print("\n✓ Example 5 complete\n")


# ==================== Example 6: Frequency Variation ====================

def example_frequency_variation():
    """
    Example 6: Test response to grid frequency variations
    - Simulate grid frequency changes (48-52 Hz)
    - Monitor electrolyser response
    """
    print("\n" + "="*70)
    print("EXAMPLE 6: Grid Frequency Variation Response")
    print("="*70)

    system = ElectrolyserControlSystem(ElectrolyserType.PEM)

    print("\n1. Starting electrolyser at 50 Hz...")
    system.start_operation()
    system.set_voltage(45.0)
    system.set_power(3500.0)
    system.electrolyser.transition_mode(OperatingMode.NORMAL)
    time.sleep(1)

    print("\n2. Varying grid frequency (48-52 Hz):")
    print(f"\n{'Time(s)':<10} {'Freq(Hz)':<12} {'Voltage(V)':<12} {'Current(A)':<12} {'Power(W)':<12}")
    print("-" * 58)

    frequencies = [48.0, 49.0, 50.0, 51.0, 52.0, 51.0, 50.0, 49.0, 48.0]

    for freq in frequencies:
        system.set_frequency(freq)

        # Operate at this frequency for 3 seconds
        for i in range(30):
            system.electrolyser.update_state(0.1)

            if i == 0:  # Print only first iteration
                status = system.get_status()
                print(f"{status['run_time']:<10.1f} {freq:<12.1f} "
                      f"{status['voltage']:<12.2f} {status['current']:<12.2f} "
                      f"{status['power']:<12.0f}")

            time.sleep(0.01)

    print("\n3. Stopping...")
    system.stop_operation()

    print("✓ Example 6 complete\n")


# ==================== Example 7: Safety Monitoring ====================

def example_safety_monitoring():
    """
    Example 7: Demonstrate safety monitoring and limits
    - Attempt to exceed voltage limits
    - Test current limits
    - Monitor safety alerts
    """
    print("\n" + "="*70)
    print("EXAMPLE 7: Safety Monitoring and Limits")
    print("="*70)

    system = ElectrolyserControlSystem(ElectrolyserType.PEM)
    specs = system.electrolyser.specs

    print(f"\nPEM Safety Limits:")
    print(f"  Voltage: {specs.min_voltage}V - {specs.max_voltage}V")
    print(f"  Current: {specs.min_current}A - {specs.max_current}A")
    print(f"  Temperature: {specs.temperature_min}°C - {specs.temperature_max}°C")
    print(f"  Pressure: {specs.pressure_min} - {specs.pressure_max} bar")

    print(f"\n1. Starting normal operation...")
    system.start_operation()
    system.set_voltage(45.0)
    system.set_power(3500.0)
    system.electrolyser.transition_mode(OperatingMode.NORMAL)
    time.sleep(1)

    status = system.get_status()
    print(f"   Safe: {status['safety']['safe']}")

    print(f"\n2. Testing voltage limits...")

    # Test normal voltage
    print(f"   Setting voltage to 45V (normal)...")
    system.set_voltage(45.0)
    status = system.get_status()
    print(f"   Safe: {status['safety']['safe']}")

    # Test high voltage
    print(f"   Attempting to set voltage to 65V (exceeds {specs.max_voltage}V limit)...")
    system.set_voltage(65.0)
    status = system.get_status()
    print(f"   Safe: {status['safety']['safe']}")
    if not status['safety']['safe']:
        print(f"   Alert: {status['safety']['alerts'][0]}")

    # Reset
    system.safety_monitor.clear()
    system.set_voltage(45.0)

    print(f"\n3. Testing current limits...")

    # Try to exceed current
    print(f"   Attempting to set power to 30000W (exceeds current limit)...")
    system.set_power(30000.0)
    status = system.get_status()
    print(f"   Safe: {status['safety']['safe']}")
    if not status['safety']['safe']:
        print(f"   Alert: {status['safety']['alerts'][0]}")

    print(f"\n4. Stopping...")
    system.stop_operation()

    print("✓ Example 7 complete\n")


# ==================== Example 8: Production Calculation ====================

def example_production_calculation():
    """
    Example 8: Calculate hydrogen and oxygen production
    - Run at different power levels
    - Calculate production rates and efficiency
    """
    print("\n" + "="*70)
    print("EXAMPLE 8: Production Calculation at Different Power Levels")
    print("="*70)

    system = ElectrolyserControlSystem(ElectrolyserType.PEM)
    system.start_operation()

    power_levels = [500, 1000, 2000, 3000, 4000, 4500]

    print(f"\n{'Power(W)':<12} {'Voltage(V)':<12} {'Current(A)':<12} "
          f"{'Eff(%)':<10} {'H2(Nm³/h)':<12} {'O2(Nm³/h)':<12}")
    print("-" * 78)

    for power in power_levels:
        system.set_power(float(power))
        system.electrolyser.transition_mode(OperatingMode.NORMAL)

        # Simulate 1 hour of operation
        for i in range(3600):
            system.electrolyser.update_state(1.0 / 3600)
            if i % 360 == 0:
                pass  # Simulate without printing

        status = system.get_status()
        specs = system.electrolyser.specs

        # Calculate production rates
        runtime_hours = status['run_time'] / 3600
        if runtime_hours > 0:
            h2_rate = status['hydrogen_produced'] / runtime_hours
            o2_rate = status['oxygen_produced'] / runtime_hours
        else:
            h2_rate = o2_rate = 0

        print(f"{power:<12} {status['voltage']:<12.2f} "
              f"{status['current']:<12.2f} {status['efficiency']:<10.1f} "
              f"{h2_rate:<12.4f} {o2_rate:<12.4f}")

        # Reset for next test
        system.electrolyser.hydrogen_produced = 0
        system.electrolyser.oxygen_produced = 0
        system.electrolyser.water_consumed = 0
        system.electrolyser.start_time = None

    system.stop_operation()

    print("\n✓ Example 8 complete\n")


# ==================== Main ====================

def main():
    """Run selected examples"""

    examples = {
        "1": ("Basic PEM Operation", example_basic_pem_operation),
        "2": ("Voltage Ramp-Up", example_voltage_ramp_up),
        "3": ("Power Ramp-Up", example_power_ramp_up),
        "4": ("Advanced Scheduling", example_advanced_scheduling),
        "5": ("Type Comparison", example_electrolyser_comparison),
        "6": ("Frequency Variation", example_frequency_variation),
        "7": ("Safety Monitoring", example_safety_monitoring),
        "8": ("Production Calculation", example_production_calculation),
        "all": ("All Examples", None),
    }

    print("\n" + "="*70)
    print("HYDROGEN ELECTROLYSER CONTROL SYSTEM - EXAMPLES")
    print("="*70)
    print("\nAvailable Examples:")
    for key, (name, _) in examples.items():
        print(f"  {key}: {name}")

    if len(sys.argv) > 1:
        choice = sys.argv[1]
    else:
        choice = input("\nSelect example (1-8 or 'all'): ").strip()

    if choice == "all":
        for key in ["1", "2", "3", "4", "5", "6", "7", "8"]:
            examples[key][1]()
            time.sleep(1)
    elif choice in examples and examples[choice][1]:
        examples[choice][1]()
    else:
        print("Invalid choice")


if __name__ == "__main__":
    main()
