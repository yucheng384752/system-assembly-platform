import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const app = fs.readFileSync(new URL("../gui/app.js", import.meta.url), "utf8");
const source = app.match(/function pkNameScore[\s\S]*?(?=function applyPkFkSuggestions)/)?.[0];
assert.ok(source, "FK detection source not found");
const cycleSource = app.match(/function edgeCreatesCycle[\s\S]*?\n}/)?.[0];
assert.ok(cycleSource, "DAG cycle detection source not found");

const sourceTable = { id: "source", tableName: "source" };
const branchB = { id: "branch-b", tableName: "branch_b" };
const branchC = { id: "branch-c", tableName: "branch_c" };
const merge = { id: "merge", tableName: "merge" };
const state = {
  uploadedTables: [sourceTable, branchB, branchC, merge],
  dataflows: [{ id: "flow-1", nodeOrder: [sourceTable.id, branchB.id, branchC.id, merge.id], edges: [] }],
  activeDataflowId: "flow-1",
  tableSchema: new Map([
    [sourceTable.id, [{ name: "line_id", isPK: true }]],
    [branchB.id, [{ name: "branch_b_id", isPK: true }, { name: "line_ref", isPK: false }]],
    [branchC.id, [{ name: "branch_c_id", isPK: true }, { name: "line_ref", isPK: false }]],
    [merge.id, [{ name: "b_ref", isPK: false }, { name: "c_ref", isPK: false }]],
  ]),
  tableData: new Map([
    [sourceTable.id, [["L-001"], ["L-002"], ["L-003"]]],
    [branchB.id, [["B-001", "L-001"], ["B-002", "L-002"], ["B-003", "L-003"]]],
    [branchC.id, [["C-001", "L-001"], ["C-002", "L-002"], ["C-003", "L-003"]]],
    [merge.id, [["B-001", "C-001"], ["B-002", "C-002"], ["B-003", "C-003"]]],
  ]),
};

const activeDataflow = () => state.dataflows[0];
const context = vm.createContext({ state, Set, Map, activeDataflow });
vm.runInContext(`${source}\n${cycleSource}\nresult = detectPkFk();`, context);
const pairs = context.result.fks.map((fk) => `${fk.targetTableId}->${fk.tableId}:${fk.colName}`);
assert.deepEqual([...pairs].sort(), [
  "branch-b->merge:b_ref",
  "branch-c->merge:c_ref",
  "source->branch-b:line_ref",
  "source->branch-c:line_ref",
]);

const dag = [
  { id: "ab", parentTableId: "source", childTableId: "branch-b" },
  { id: "ac", parentTableId: "source", childTableId: "branch-c" },
  { id: "bd", parentTableId: "branch-b", childTableId: "merge" },
  { id: "cd", parentTableId: "branch-c", childTableId: "merge" },
];
assert.equal(context.edgeCreatesCycle(dag, "merge", "source"), true);
assert.equal(context.edgeCreatesCycle(dag, "branch-b", "branch-c"), false);
console.log("OK FK branch/merge detection and DAG cycle rejection");
