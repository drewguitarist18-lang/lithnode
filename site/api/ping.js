// The Lithnode app's one ping per version: {kind: "install" | "update", v: "0.1.24", os: "win" | "mac" | "linux"}.
// Counted by day, OS and version (_count.js); nothing about the person, no IP, no ID. The app's Settings can turn it off.
const { record } = require("./_count");

const OS = ["win", "mac", "linux"];

module.exports = async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  if (req.method !== "POST") return res.status(405).end();
  if (!/^Lithnode\//.test(req.headers["user-agent"] || "")) return res.status(204).end();
  let body = req.body;
  if (typeof body === "string") { try { body = JSON.parse(body); } catch { body = {}; } }
  body = body || {};
  const kind = { install: "i", update: "u" }[body.kind];
  const v = typeof body.v === "string" && /^\d{1,3}\.\d{1,3}\.\d{1,4}$/.test(body.v) ? body.v : "";
  if (kind && v && OS.includes(body.os)) await record(kind, [body.os, v]);
  res.status(204).end();
};
