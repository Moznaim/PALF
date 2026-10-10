// ecosystem.config.js  –  PM2 process configuration
//
// Usage:
//   pm2 start ecosystem.config.js        ← start all processes
//   pm2 restart all                      ← restart all
//   pm2 logs                             ← view combined logs
//   pm2 save && pm2 startup              ← persist across reboots

const fs = require("fs");
const path = require("path");

// Use backend virtual environment Python if available, otherwise fall back to system python3
const venvPythonLinux = path.resolve("./backend/venv/bin/python3");
const venvPythonWin   = path.resolve("./backend/venv/Scripts/python.exe");

let pythonCmd = "python3";
if (fs.existsSync(venvPythonLinux)) {
  pythonCmd = venvPythonLinux;
} else if (fs.existsSync(venvPythonWin)) {
  pythonCmd = venvPythonWin;
}

module.exports = {
  apps: [
    {
      name: "palf-vision",
      script: "node_modules/.bin/next",
      args:   "start",
      cwd:    "./",
      env: {
        NODE_ENV: "production",
        PORT:     3000,
      },
      autorestart:   true,
      watch:         false,
      max_restarts:  10,
      restart_delay: 3000,
      out_file:      "./logs/out.log",
      error_file:    "./logs/error.log",
      merge_logs:    true,
      log_date_format: "YYYY-MM-DD HH:mm:ss",
    },
    {
      name: "palf-camera",
      script: "scripts/camera_service.py",
      interpreter: pythonCmd,
      cwd:    "./",
      autorestart:   true,
      watch:         false,
      max_restarts:  10,
      restart_delay: 3000,
      out_file:      "./logs/camera_out.log",
      error_file:    "./logs/camera_error.log",
      merge_logs:    true,
      log_date_format: "YYYY-MM-DD HH:mm:ss",
    },
    {
      name: "palf-api",
      script: "main.py",
      interpreter: pythonCmd,
      cwd:    "./backend",
      autorestart:   true,
      watch:         false,
      max_restarts:  10,
      restart_delay: 3000,
      out_file:      "../logs/api_out.log",
      error_file:    "../logs/api_error.log",
      merge_logs:    true,
      log_date_format: "YYYY-MM-DD HH:mm:ss",
    },
  ],
};
