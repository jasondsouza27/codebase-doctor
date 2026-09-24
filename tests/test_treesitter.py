"""
Unit tests for Tree-sitter AST parsing across JavaScript, TypeScript, C/C++/Arduino, and Go,
including fallback mechanisms.
"""

from pathlib import Path
from codebase_doctor.models import EdgeType, SymbolType
from codebase_doctor.parser import (
    CodeParser,
    _TreeSitterCppVisitor,
    _TreeSitterGoVisitor,
    _TreeSitterJSVisitor,
    _HAS_TREE_SITTER,
)


def test_treesitter_javascript_ast_extraction():
    js_code = """
import { formatCurrency } from './utils';
const axios = require('axios');

export class PaymentClient extends BaseClient {
    async processPayment(amount) {
        if (amount <= 0) {
            throw new Error("Invalid amount");
        }
        return await axios.post('/pay', { amount });
    }
}

export const calculateTax = (amount, rate = 0.1) => {
    return amount * rate;
};

export async function verifySignature(sig) {
    return sig.length > 0;
}
"""
    visitor = _TreeSitterJSVisitor("client", "src/client.js", js_code)
    symbols, edges = visitor.parse()

    names = {s.name: s for s in symbols}
    assert "client" in names
    assert "PaymentClient" in names
    assert names["PaymentClient"].symbol_type == SymbolType.CLASS
    assert "processPayment" in names
    assert names["processPayment"].symbol_type == SymbolType.METHOD
    assert names["processPayment"].complexity > 1

    assert "calculateTax" in names
    assert names["calculateTax"].symbol_type == SymbolType.FUNCTION
    assert "amount" in names["calculateTax"].parameters

    assert "verifySignature" in names
    assert names["verifySignature"].symbol_type == SymbolType.FUNCTION

    # Check edges
    edge_types = {e.edge_type for e in edges}
    assert EdgeType.IMPORTS in edge_types
    assert EdgeType.DEFINES in edge_types
    assert EdgeType.INHERITS in edge_types
    assert EdgeType.CALLS in edge_types

    assert any(e.edge_type == EdgeType.IMPORTS and e.target == "./utils" for e in edges)
    assert any(e.edge_type == EdgeType.IMPORTS and e.target == "axios" for e in edges)
    assert any(e.edge_type == EdgeType.INHERITS and e.target == "BaseClient" for e in edges)
    assert any(e.edge_type == EdgeType.CALLS and "axios.post" in e.target for e in edges)


def test_treesitter_typescript_and_tsx():
    ts_code = """
import React, { useState } from 'react';
import { User } from '../types';

export interface UserProps {
    id: string;
    name: string;
}

export class UserService {
    getUser(id: string): User {
        return { id, name: "Admin" };
    }
}

export const UserCard = ({ id, name }: UserProps) => {
    return <div>{name}</div>;
};
"""
    visitor = _TreeSitterJSVisitor("user_view", "src/UserView.tsx", ts_code)
    symbols, edges = visitor.parse()

    names = {s.name: s for s in symbols}
    assert "UserProps" in names
    assert names["UserProps"].symbol_type == SymbolType.INTERFACE
    assert "UserService" in names
    assert names["UserService"].symbol_type == SymbolType.CLASS
    assert "getUser" in names
    assert names["getUser"].symbol_type == SymbolType.METHOD
    assert "UserCard" in names
    assert names["UserCard"].symbol_type == SymbolType.FUNCTION

    assert any(e.edge_type == EdgeType.IMPORTS and e.target == "react" for e in edges)
    assert any(e.edge_type == EdgeType.IMPORTS and e.target == "../types" for e in edges)


def test_treesitter_cpp_arduino_ast_extraction():
    cpp_code = """
#include "sensor_config.h"
#include <WiFi.h>

struct SensorPacket {
    int sensorId;
    float reading;
};

class SensorManager : public BaseManager {
public:
    void init() {
        Serial.begin(115200);
    }
};

void setup() {
    Serial.println("Ready");
}

void loop() {
    delay(100);
}
"""
    visitor = _TreeSitterCppVisitor("firmware", "esp32/firmware.ino", cpp_code)
    symbols, edges = visitor.parse()

    names = {s.name: s for s in symbols}
    assert "firmware" in names
    assert "SensorPacket" in names
    assert names["SensorPacket"].symbol_type == SymbolType.STRUCT
    assert "SensorManager" in names
    assert names["SensorManager"].symbol_type == SymbolType.CLASS
    assert "init" in names
    assert names["init"].symbol_type == SymbolType.METHOD
    assert "setup" in names
    assert names["setup"].symbol_type == SymbolType.FUNCTION
    assert "loop" in names
    assert names["loop"].symbol_type == SymbolType.FUNCTION

    edge_types = {e.edge_type for e in edges}
    assert EdgeType.INCLUDES in edge_types
    assert EdgeType.DEFINES in edge_types
    assert EdgeType.INHERITS in edge_types
    assert EdgeType.CALLS in edge_types

    assert any(e.edge_type == EdgeType.INCLUDES and e.target == "sensor_config.h" for e in edges)
    assert any(e.edge_type == EdgeType.INCLUDES and e.target == "WiFi.h" for e in edges)
    assert any(e.edge_type == EdgeType.INHERITS and e.target == "BaseManager" for e in edges)
    assert any(e.edge_type == EdgeType.CALLS and "Serial.begin" in e.target for e in edges)


def test_treesitter_go_ast_extraction():
    go_code = """
package main

import (
    "fmt"
    "net/http"
)

type Config struct {
    Port int
}

type Service interface {
    Run() error
}

func (c *Config) StartServer(host string) error {
    if host == "" {
        host = "localhost"
    }
    fmt.Println(host)
    return nil
}

func ProcessRequest(req *http.Request) {
    c := Config{}
    c.StartServer("localhost")
}
"""
    visitor = _TreeSitterGoVisitor("server", "cmd/server.go", go_code)
    symbols, edges = visitor.parse()

    names = {s.name: s for s in symbols}
    assert "server" in names
    assert "Config" in names
    assert names["Config"].symbol_type == SymbolType.STRUCT
    assert "Service" in names
    assert names["Service"].symbol_type == SymbolType.INTERFACE
    assert "StartServer" in names
    assert names["StartServer"].symbol_type == SymbolType.METHOD
    assert names["StartServer"].complexity > 1
    assert "ProcessRequest" in names
    assert names["ProcessRequest"].symbol_type == SymbolType.FUNCTION

    edge_types = {e.edge_type for e in edges}
    assert EdgeType.IMPORTS in edge_types
    assert EdgeType.DEFINES in edge_types
    assert EdgeType.CALLS in edge_types

    assert any(e.edge_type == EdgeType.IMPORTS and e.target == "fmt" for e in edges)
    assert any(e.edge_type == EdgeType.IMPORTS and e.target == "net/http" for e in edges)
    assert any(e.edge_type == EdgeType.CALLS and "fmt.Println" in e.target for e in edges)


def test_parser_end_to_end_uses_treesitter_or_fallback(monkeypatch):
    parser = CodeParser(repo_root=Path("."))

    # 1. Normal execution
    symbols, edges = parser.parse_file(
        Path("test.go"),
        source_code="package main\ntype S struct {}\nfunc Foo() {}\n",
    )
    names = {s.name for s in symbols}
    assert "S" in names
    assert "Foo" in names

    # 2. Verify graceful fallback when _HAS_TREE_SITTER is False
    import codebase_doctor.parser as p_module
    monkeypatch.setattr(p_module, "_HAS_TREE_SITTER", False)

    fallback_symbols, fallback_edges = parser.parse_file(
        Path("test.go"),
        source_code="package main\ntype S struct {}\nfunc Foo() {}\n",
    )
    fb_names = {s.name for s in fallback_symbols}
    assert "S" in fb_names
    assert "Foo" in fb_names
