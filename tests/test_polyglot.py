"""
Comprehensive Polyglot Integration Tests for AI Codebase Doctor.
Tests multi-language parsing, cross-language dependency graphing,
polyglot risk auditing, impact prediction, and automated test execution.
"""

from pathlib import Path
from codebase_doctor.doctor import CodebaseDoctor
from codebase_doctor.models import EdgeType, RiskCategory, RiskSeverity, SymbolType
from codebase_doctor.parser import CodeParser
from codebase_doctor.repo_manager import RepoManager
from codebase_doctor.risk_analyzer import RiskAnalyzer


def test_polyglot_file_discovery_and_language_detection():
    mgr = RepoManager("demo_repo")
    files = mgr.get_source_files()
    rel_files = [mgr.get_relative_path(f) for f in files]

    # Verify discovery across languages
    assert any(f.endswith(".py") for f in rel_files)
    assert any(f.endswith(".ino") for f in rel_files)
    assert any(f.endswith(".h") for f in rel_files)
    assert any(f.endswith(".js") for f in rel_files)
    assert any(f.endswith(".sql") for f in rel_files)

    # Language mapping
    assert mgr.detect_language("esp32/serial_bridge.ino") == "Arduino/C++"
    assert mgr.detect_language("esp32/serial_bridge.h") == "C/C++ Header"
    assert mgr.detect_language("frontend/payment_dashboard.js") == "JavaScript"
    assert mgr.detect_language("db/schema.sql") == "SQL"
    assert mgr.detect_language("payment_service.py") == "Python"

    # Languages count
    langs = mgr.get_languages()
    assert "Python" in langs
    assert "Arduino/C++" in langs
    assert "JavaScript" in langs
    assert "SQL" in langs


def test_polyglot_parser_cpp_arduino():
    code = '''
#include "sensor_config.h"
#include <WiFi.h>

struct Packet {
    int id;
};

class SensorManager : public BaseManager {
public:
    void setupSensors() {
        Serial.begin(115200);
    }
};

void setup() {
    Serial.println("Starting");
}

void loop() {
    delay(50);
}
'''
    parser = CodeParser(repo_root=Path("."))
    symbols, edges = parser.parse_file(Path("esp32/firmware.ino"), source_code=code)

    names = {s.name: s for s in symbols}
    assert "firmware" in names or "esp32.firmware" in [s.qualified_name for s in symbols]
    assert "Packet" in names
    assert names["Packet"].symbol_type == SymbolType.STRUCT
    assert "SensorManager" in names
    assert names["SensorManager"].symbol_type == SymbolType.CLASS
    assert "setup" in names
    assert names["setup"].symbol_type == SymbolType.FUNCTION
    assert "loop" in names
    assert names["loop"].symbol_type == SymbolType.FUNCTION

    # Check edges
    edge_types = {e.edge_type for e in edges}
    assert EdgeType.INCLUDES in edge_types
    assert EdgeType.DEFINES in edge_types
    assert EdgeType.CALLS in edge_types


def test_polyglot_parser_javascript():
    code = '''
import { formatCurrency } from './utils';
const axios = require('axios');

export class PaymentClient extends BaseClient {
    async processPayment(amount) {
        return await axios.post('/pay', { amount });
    }
}

export async function verifySignature(sig) {
    return sig.length > 0;
}
'''
    parser = CodeParser(repo_root=Path("."))
    symbols, edges = parser.parse_file(Path("client.js"), source_code=code)

    names = {s.name: s for s in symbols}
    assert "PaymentClient" in names
    assert names["PaymentClient"].symbol_type == SymbolType.CLASS
    assert "verifySignature" in names
    assert names["verifySignature"].symbol_type == SymbolType.FUNCTION

    edge_types = {e.edge_type for e in edges}
    assert EdgeType.IMPORTS in edge_types
    assert EdgeType.DEFINES in edge_types
    assert EdgeType.CALLS in edge_types


def test_polyglot_parser_sql():
    code = '''
CREATE TABLE IF NOT EXISTS accounts (
    id INT PRIMARY KEY,
    name VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS orders (
    order_id INT PRIMARY KEY,
    account_id INT,
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);
'''
    parser = CodeParser(repo_root=Path("."))
    symbols, edges = parser.parse_file(Path("db.sql"), source_code=code)

    names = {s.name: s for s in symbols}
    assert "accounts" in names
    assert names["accounts"].symbol_type == SymbolType.SCHEMA
    assert "orders" in names
    assert names["orders"].symbol_type == SymbolType.SCHEMA

    # References edge
    assert any(e.edge_type == EdgeType.REFERENCES and e.target == "accounts" for e in edges)


def test_polyglot_risk_analyzer_memory_and_hardware():
    analyzer = RiskAnalyzer()

    # C++ buffer overflow
    c_code = '''
void copyBuffer(char* src) {
    char dest[16];
    strcpy(dest, src);
}
'''
    c_risks = analyzer.analyze_file("firmware.cpp", c_code)
    assert any("buffer" in r.title.lower() or "strcpy" in r.description.lower() for r in c_risks)

    # Arduino blocking delay
    ino_code = '''
void loop() {
    delay(2000);
}
'''
    ino_risks = analyzer.analyze_file("sensor.ino", ino_code)
    assert any("delay" in r.title.lower() for r in ino_risks)

    # JS eval code execution
    js_code = 'eval("var x = " + userInput);'
    js_risks = analyzer.analyze_file("app.js", js_code)
    assert any("eval" in r.title.lower() for r in js_risks)

    # Hardcoded secret in non-python file
    cfg_code = 'auth_token: "sk_test_9999888877776666"'
    cfg_risks = analyzer.analyze_file("config.yaml", cfg_code)
    assert any("secret" in r.title.lower() for r in cfg_risks)


def test_polyglot_impact_analysis_arduino():
    doctor = CodebaseDoctor(repo_path="demo_repo")
    doctor.scan()

    report = doctor.analyze_change("esp32/serial_bridge.ino")
    assert report.blast_radius_score > 0
    assert len(report.suggested_tests) > 0
    assert any("handshake" in t or "serial" in t or "baud" in t for t in report.suggested_tests)


def test_polyglot_impact_analysis_javascript():
    doctor = CodebaseDoctor(repo_path="demo_repo")
    doctor.scan()

    report = doctor.analyze_change("frontend/payment_dashboard.js")
    assert report.blast_radius_score > 0
    assert len(report.suggested_tests) > 0


def test_polyglot_test_generation_and_execution(tmp_path):
    doctor = CodebaseDoctor(repo_path="demo_repo")
    doctor.scan()

    report = doctor.analyze_change("esp32/serial_bridge.ino")
    execution, test_path = doctor.generate_and_run_tests(report, output_dir=tmp_path)

    assert execution.total > 0
    assert execution.passed >= 1
    assert execution.failed == 0
    assert execution.pass_rate == 100.0
    assert test_path.exists()


def test_polyglot_doctor_scan_and_graph_statistics():
    doctor = CodebaseDoctor(repo_path="demo_repo")
    stats = doctor.scan()

    assert stats["total_files"] >= 8
    assert "languages" in stats
    assert "Python" in stats["languages"]
    assert "Arduino/C++" in stats["languages"] or "C/C++ Header" in stats["languages"]


def test_polyglot_parser_cpp_allman_and_multiline_params():
    code = '''
// Pin for DHT11 data
// Function to stabilize sensor readings
String status = "Pump relay initialized (OFF)";

void setup()
{
    Serial.begin(115200);
}

void processTransaction(
    int accountId,
    float amount,
    const String& note
) {
    Serial.println(amount);
}

void loop()
{
    delay(50);
}
'''
    parser = CodeParser(repo_root=Path("."))
    symbols, edges = parser.parse_file(Path("firmware.cpp"), source_code=code)
    names = {s.name: s for s in symbols}

    # Verify Allman braces and multiline parameters are extracted
    assert "setup" in names
    assert names["setup"].symbol_type == SymbolType.FUNCTION
    assert "processTransaction" in names
    assert names["processTransaction"].symbol_type == SymbolType.FUNCTION
    assert "loop" in names

    # Verify comments and string contents did not generate fake symbols
    assert "data" not in names
    assert "stabilize" not in names
    assert "initialized" not in names
    assert "OFF" not in names


def test_polyglot_parser_js_multiline_arrow_and_react():
    code = '''
import { api } from "../lib/api";

const url = "http://api.internal:8080/v1"; // Internal API URL

export const Dashboard = ({
    user,
    role,
}: DashboardProps) => {
    return null;
};

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
    ({ className, variant }, ref) => {
        return null;
    }
);

async function fetchSensorData(
    sensorId: string,
    limit: number
) {
    return [];
}
'''
    parser = CodeParser(repo_root=Path("."))
    symbols, edges = parser.parse_file(Path("frontend/src/pages/Dashboard.tsx"), source_code=code)
    names = {s.name: s for s in symbols}

    assert "Dashboard" in names
    assert names["Dashboard"].symbol_type == SymbolType.FUNCTION
    assert "Button" in names
    assert names["Button"].symbol_type == SymbolType.FUNCTION
    assert "fetchSensorData" in names
    assert names["fetchSensorData"].symbol_type == SymbolType.FUNCTION

    # Slashes inside url string shouldn't break subsequent lines
    assert any(e.edge_type == EdgeType.IMPORTS and e.target == "../lib/api" for e in edges)


def test_polyglot_graph_relative_path_resolution_and_dotdot():
    from codebase_doctor.graph import CodeGraph
    from codebase_doctor.models import DependencyEdge, EdgeType, Symbol, SymbolType

    graph = CodeGraph()

    # Add api.ts symbol
    graph.add_symbol(
        Symbol(
            name="api",
            qualified_name="frontend.src.lib.api",
            symbol_type=SymbolType.MODULE,
            file_path="frontend/src/lib/api.ts",
            line_start=1,
            line_end=10,
            language="typescript",
        )
    )

    # Add Dashboard.tsx symbol
    graph.add_symbol(
        Symbol(
            name="Dashboard",
            qualified_name="frontend.src.pages.Dashboard",
            symbol_type=SymbolType.MODULE,
            file_path="frontend/src/pages/Dashboard.tsx",
            line_start=1,
            line_end=30,
            language="typescript",
        )
    )

    # Add import edge from Dashboard.tsx with ../ parent path traversal
    graph.add_edge(
        DependencyEdge(
            source="frontend.src.pages.Dashboard",
            target="../lib/api",
            edge_type=EdgeType.IMPORTS,
            line_number=1,
        )
    )

    graph.rebuild_file_level_graph()

    # Verify file-level edge was created
    assert graph.file_level_graph.has_edge("frontend/src/pages/Dashboard.tsx", "frontend/src/lib/api.ts")

    # Verify context-aware resolution does not match common short names globally
    res = graph._resolve_target("data", source="frontend/src/pages/Dashboard.tsx", edge_type=EdgeType.CALLS)
    assert res == "data"

