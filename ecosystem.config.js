// ecosystem.config.js  –  PM2 process configuration
//
// Usage:
//   pm2 start ecosystem.config.js        ← start all processes
//   pm2 restart all                      ← restart all
//   pm2 logs                             ← view combined logs
//   pm2 save && pm2 startup              ← persist across reboots

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
      script: "python3",
      args:   "scripts/camera_service.py",
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
      script: "python3",
      args:   "-m uvicorn main:app --app-dir . --host 0.0.0.0 --port 4000",
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
