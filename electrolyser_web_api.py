"""
Electrolyser Web API Interface
RESTful API for remote control and monitoring of hydrogen electrolysers
Built with Flask for easy integration
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
import re
from typing import Dict, Any
from datetime import datetime

from electrolyser_advanced_control import (
    AdvancedElectrolyserController,
    RampProfile,
    ElectrolyserType,
    OperationEvent
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask app setup
app = Flask(__name__)
CORS(app)

# Global controller instance
controller: AdvancedElectrolyserController = None


def init_api(electrolyser_type: ElectrolyserType = ElectrolyserType.PEM):
    """Initialize the API with an electrolyser"""
    global controller
    controller = AdvancedElectrolyserController(electrolyser_type)
    logger.info(f"API initialized with {electrolyser_type.value} electrolyser")


# ==================== Health & Status Endpoints ====================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "electrolyser_type": controller.system.electrolyser.specs.type.value if controller else None,
        "running": controller.is_running if controller else False
    })


@app.route('/api/status', methods=['GET'])
def get_status():
    """Get current electrolyser status"""
    if not controller:
        return jsonify({"error": "Controller not initialized"}), 500

    status = controller.get_real_time_status()
    if not status:
        return jsonify({"error": "No status available"}), 503

    return jsonify(status)


@app.route('/api/specs', methods=['GET'])
def get_specs():
    """Get electrolyser specifications"""
    if not controller:
        return jsonify({"error": "Controller not initialized"}), 500

    specs = controller.system.electrolyser.specs
    return jsonify({
        "type": specs.type.value,
        "nominal_voltage": specs.nominal_voltage,
        "nominal_current": specs.nominal_current,
        "nominal_power": specs.nominal_power,
        "min_voltage": specs.min_voltage,
        "max_voltage": specs.max_voltage,
        "min_current": specs.min_current,
        "max_current": specs.max_current,
        "hydrogen_production_rate": specs.hydrogen_production_rate,
        "oxygen_production_rate": specs.oxygen_production_rate,
        "water_consumption_rate": specs.water_consumption_rate,
        "temperature_range": [specs.temperature_min, specs.temperature_max],
        "pressure_range": [specs.pressure_min, specs.pressure_max]
    })


# ==================== Control Endpoints ====================

@app.route('/api/control/start', methods=['POST'])
def start_operation():
    """Start electrolyser operation"""
    if not controller:
        return jsonify({"error": "Controller not initialized"}), 500

    try:
        controller.start()
        return jsonify({"status": "started", "timestamp": datetime.now().isoformat()})
    except Exception as e:
        logger.error(f"Start error: {e}")
        return jsonify({"error": str(e)}), 400


@app.route('/api/control/stop', methods=['POST'])
def stop_operation():
    """Stop electrolyser operation"""
    if not controller:
        return jsonify({"error": "Controller not initialized"}), 500

    try:
        controller.stop()
        return jsonify({"status": "stopped", "timestamp": datetime.now().isoformat()})
    except Exception as e:
        logger.error(f"Stop error: {e}")
        return jsonify({"error": str(e)}), 400


@app.route('/api/control/voltage', methods=['POST'])
def set_voltage():
    """Set electrolyser voltage"""
    if not controller:
        return jsonify({"error": "Controller not initialized"}), 500

    data = request.get_json()
    if not data or 'voltage' not in data:
        return jsonify({"error": "Missing 'voltage' parameter"}), 400

    voltage = data.get('voltage')
    try:
        success = controller.system.set_voltage(voltage)
        return jsonify({
            "success": success,
            "voltage": voltage,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Voltage set error: {e}")
        return jsonify({"error": str(e)}), 400


@app.route('/api/control/power', methods=['POST'])
def set_power():
    """Set electrolyser power"""
    if not controller:
        return jsonify({"error": "Controller not initialized"}), 500

    data = request.get_json()
    if not data or 'power' not in data:
        return jsonify({"error": "Missing 'power' parameter"}), 400

    power = data.get('power')
    try:
        success = controller.system.set_power(power)
        return jsonify({
            "success": success,
            "power": power,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Power set error: {e}")
        return jsonify({"error": str(e)}), 400


@app.route('/api/control/frequency', methods=['POST'])
def set_frequency():
    """Set inverter frequency"""
    if not controller:
        return jsonify({"error": "Controller not initialized"}), 500

    data = request.get_json()
    if not data or 'frequency' not in data:
        return jsonify({"error": "Missing 'frequency' parameter"}), 400

    frequency = data.get('frequency')
    try:
        success = controller.system.set_frequency(frequency)
        return jsonify({
            "success": success,
            "frequency": frequency,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Frequency set error: {e}")
        return jsonify({"error": str(e)}), 400


# ==================== Scheduling Endpoints ====================

@app.route('/api/schedule/power-ramp', methods=['POST'])
def set_power_ramp():
    """Set power ramp schedule"""
    if not controller:
        return jsonify({"error": "Controller not initialized"}), 500

    data = request.get_json()
    required = ['start_power', 'end_power', 'duration']
    if not data or not all(k in data for k in required):
        return jsonify({"error": f"Missing parameters: {required}"}), 400

    try:
        profile_str = data.get('profile', 'LINEAR').upper()
        profile = RampProfile[profile_str]

        controller.set_power_ramp(
            start_power=data['start_power'],
            end_power=data['end_power'],
            duration=data['duration'],
            profile=profile
        )

        return jsonify({
            "status": "scheduled",
            "power_ramp": {
                "start": data['start_power'],
                "end": data['end_power'],
                "duration": data['duration'],
                "profile": profile_str
            },
            "timestamp": datetime.now().isoformat()
        })
    except KeyError as e:
        return jsonify({"error": f"Invalid profile: {e}"}), 400
    except Exception as e:
        logger.error(f"Power ramp error: {e}")
        return jsonify({"error": str(e)}), 400


@app.route('/api/schedule/voltage-ramp', methods=['POST'])
def set_voltage_ramp():
    """Set voltage ramp schedule"""
    if not controller:
        return jsonify({"error": "Controller not initialized"}), 500

    data = request.get_json()
    required = ['start_voltage', 'end_voltage', 'duration']
    if not data or not all(k in data for k in required):
        return jsonify({"error": f"Missing parameters: {required}"}), 400

    try:
        profile_str = data.get('profile', 'LINEAR').upper()
        profile = RampProfile[profile_str]

        controller.set_voltage_ramp(
            start_voltage=data['start_voltage'],
            end_voltage=data['end_voltage'],
            duration=data['duration'],
            profile=profile
        )

        return jsonify({
            "status": "scheduled",
            "voltage_ramp": {
                "start": data['start_voltage'],
                "end": data['end_voltage'],
                "duration": data['duration'],
                "profile": profile_str
            },
            "timestamp": datetime.now().isoformat()
        })
    except KeyError as e:
        return jsonify({"error": f"Invalid profile: {e}"}), 400
    except Exception as e:
        logger.error(f"Voltage ramp error: {e}")
        return jsonify({"error": str(e)}), 400


# ==================== Monitoring Endpoints ====================

@app.route('/api/monitoring/safety', methods=['GET'])
def get_safety_status():
    """Get safety status"""
    if not controller:
        return jsonify({"error": "Controller not initialized"}), 500

    status = controller.get_real_time_status()
    if not status:
        return jsonify({"error": "No status available"}), 503

    safety = status.get('safety', {})
    return jsonify({
        "safe": safety.get('safe', False),
        "alerts": safety.get('alerts', []),
        "warnings": safety.get('warnings', []),
        "timestamp": datetime.now().isoformat()
    })


@app.route('/api/monitoring/summary', methods=['GET'])
def get_summary():
    """Get operation summary"""
    if not controller:
        return jsonify({"error": "Controller not initialized"}), 500

    summary = controller.logger.get_summary()
    return jsonify(summary)


@app.route('/api/monitoring/production', methods=['GET'])
def get_production():
    """Get hydrogen/oxygen production data"""
    if not controller:
        return jsonify({"error": "Controller not initialized"}), 500

    status = controller.get_real_time_status()
    if not status:
        return jsonify({"error": "No status available"}), 503

    return jsonify({
        "hydrogen_produced_nm3": status['hydrogen_produced'],
        "oxygen_produced_nm3": status['oxygen_produced'],
        "water_consumed_liters": status['water_consumed'],
        "efficiency_percent": status['efficiency'],
        "timestamp": datetime.now().isoformat()
    })


@app.route('/api/monitoring/performance', methods=['GET'])
def get_performance():
    """Get performance metrics"""
    if not controller:
        return jsonify({"error": "Controller not initialized"}), 500

    status = controller.get_real_time_status()
    if not status:
        return jsonify({"error": "No status available"}), 503

    return jsonify({
        "voltage": status['voltage'],
        "current": status['current'],
        "power": status['power'],
        "efficiency": status['efficiency'],
        "temperature": status['temperature'],
        "pressure": status['pressure'],
        "run_time": status['run_time'],
        "mode": status['mode'],
        "timestamp": datetime.now().isoformat()
    })


# ==================== Data Export Endpoints ====================

# A report name is a plain file name in the server's working directory: no
# directory component, no traversal, no hidden files, .json only. Anything else
# would let an API caller write the report to an arbitrary path on the host.
_SAFE_REPORT_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]*\.json$')


def _safe_report_filename(name) -> str:
    """Validate a client-supplied report file name; raise ValueError if unsafe."""
    if not isinstance(name, str) or not _SAFE_REPORT_NAME.match(name) or '..' in name:
        raise ValueError("filename must be a plain *.json name without directories")
    return name


@app.route('/api/export/report', methods=['POST'])
def export_report():
    """Export operation report"""
    if not controller:
        return jsonify({"error": "Controller not initialized"}), 500

    try:
        data = request.get_json(silent=True) or {}
        filename = _safe_report_filename(data.get('filename', 'electrolyser_report.json'))
        report = controller.export_report(filename)
        return jsonify({
            "status": "exported",
            "filename": filename,
            "report": report
        })
    except Exception as e:
        logger.error(f"Export error: {e}")
        return jsonify({"error": str(e)}), 400


@app.route('/api/export/csv', methods=['GET'])
def get_csv_file():
    """Get CSV log file path"""
    if not controller:
        return jsonify({"error": "Controller not initialized"}), 500

    return jsonify({
        "csv_file": controller.logger.csv_file,
        "json_file": controller.logger.json_file
    })


# ==================== Configuration Endpoints ====================

@app.route('/api/config/update-interval', methods=['POST'])
def set_update_interval():
    """Set monitoring update interval"""
    if not controller:
        return jsonify({"error": "Controller not initialized"}), 500

    data = request.get_json()
    if not data or 'interval' not in data:
        return jsonify({"error": "Missing 'interval' parameter"}), 400

    try:
        interval = float(data['interval'])
        controller.update_interval = interval
        return jsonify({
            "status": "updated",
            "interval": interval,
            "timestamp": datetime.now().isoformat()
        })
    except ValueError:
        return jsonify({"error": "Invalid interval value"}), 400


# ==================== Emergency Endpoints ====================

@app.route('/api/emergency/stop', methods=['POST'])
def emergency_stop():
    """Emergency stop"""
    if not controller:
        return jsonify({"error": "Controller not initialized"}), 500

    reason = request.get_json().get('reason', 'Manual emergency stop') if request.get_json() else 'Manual emergency stop'
    controller.safety_interlocks.trigger_emergency_stop(reason)

    return jsonify({
        "status": "emergency_stop_triggered",
        "reason": reason,
        "timestamp": datetime.now().isoformat()
    })


@app.route('/api/emergency/clear', methods=['POST'])
def clear_emergency():
    """Clear emergency stop"""
    if not controller:
        return jsonify({"error": "Controller not initialized"}), 500

    controller.safety_interlocks.clear_emergency_stop()
    return jsonify({
        "status": "emergency_cleared",
        "timestamp": datetime.now().isoformat()
    })


# ==================== WebSocket-like Polling (for real-time data) ====================

@app.route('/api/stream/status', methods=['GET'])
def stream_status():
    """Stream live status (polling endpoint)"""
    if not controller:
        return jsonify({"error": "Controller not initialized"}), 500

    status = controller.get_real_time_status()
    if not status:
        return jsonify({"error": "No status available"}), 503

    return jsonify({
        "data": status,
        "timestamp": datetime.now().isoformat()
    })


# ==================== Example Client ====================

class ElectrolyserClient:
    """Python client for the electrolyser API"""

    def __init__(self, base_url: str = "http://localhost:5000"):
        self.base_url = base_url
        import requests
        self.requests = requests

    def health_check(self) -> Dict:
        """Check API health"""
        resp = self.requests.get(f"{self.base_url}/api/health")
        return resp.json()

    def get_status(self) -> Dict:
        """Get current status"""
        resp = self.requests.get(f"{self.base_url}/api/status")
        return resp.json()

    def start(self) -> Dict:
        """Start operation"""
        resp = self.requests.post(f"{self.base_url}/api/control/start")
        return resp.json()

    def stop(self) -> Dict:
        """Stop operation"""
        resp = self.requests.post(f"{self.base_url}/api/control/stop")
        return resp.json()

    def set_voltage(self, voltage: float) -> Dict:
        """Set voltage"""
        resp = self.requests.post(
            f"{self.base_url}/api/control/voltage",
            json={"voltage": voltage}
        )
        return resp.json()

    def set_power(self, power: float) -> Dict:
        """Set power"""
        resp = self.requests.post(
            f"{self.base_url}/api/control/power",
            json={"power": power}
        )
        return resp.json()

    def set_power_ramp(self, start: float, end: float, duration: float, profile: str = "LINEAR") -> Dict:
        """Set power ramp"""
        resp = self.requests.post(
            f"{self.base_url}/api/schedule/power-ramp",
            json={
                "start_power": start,
                "end_power": end,
                "duration": duration,
                "profile": profile
            }
        )
        return resp.json()

    def set_frequency(self, frequency: float) -> Dict:
        """Set frequency"""
        resp = self.requests.post(
            f"{self.base_url}/api/control/frequency",
            json={"frequency": frequency}
        )
        return resp.json()

    def get_production(self) -> Dict:
        """Get production metrics"""
        resp = self.requests.get(f"{self.base_url}/api/monitoring/production")
        return resp.json()

    def emergency_stop(self, reason: str = "Manual stop") -> Dict:
        """Emergency stop"""
        resp = self.requests.post(
            f"{self.base_url}/api/emergency/stop",
            json={"reason": reason}
        )
        return resp.json()


# ==================== Server Runner ====================

def run_server(host: str = "0.0.0.0", port: int = 5000, electrolyser_type: str = "PEM"):
    """Run the API server"""
    try:
        electrolyser = ElectrolyserType[electrolyser_type.upper()]
    except KeyError:
        print(f"Unknown electrolyser type: {electrolyser_type}")
        return

    init_api(electrolyser)

    print(f"\n" + "="*70)
    print(f"Electrolyser Web API Server")
    print(f"Type: {electrolyser_type}")
    print(f"Starting on {host}:{port}")
    print(f"="*70)
    print(f"\nAPI Documentation:")
    print(f"  GET  /api/health - Health check")
    print(f"  GET  /api/status - Current status")
    print(f"  POST /api/control/start - Start operation")
    print(f"  POST /api/control/stop - Stop operation")
    print(f"  POST /api/control/voltage - Set voltage")
    print(f"  POST /api/control/power - Set power")
    print(f"  POST /api/control/frequency - Set frequency")
    print(f"  POST /api/schedule/power-ramp - Schedule power ramp")
    print(f"  POST /api/schedule/voltage-ramp - Schedule voltage ramp")
    print(f"  GET  /api/monitoring/safety - Safety status")
    print(f"  GET  /api/monitoring/production - Production data")
    print(f"  GET  /api/monitoring/performance - Performance metrics")
    print(f"\nAPI running at http://{host}:{port}")
    print(f"="*70 + "\n")

    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    import sys

    electrolyser_type = sys.argv[1] if len(sys.argv) > 1 else "PEM"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 5000

    run_server(electrolyser_type=electrolyser_type, port=port)
