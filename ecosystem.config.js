// ecosystem.config.js  –  PM2 process configuration
//
// Usage:
//   pm2 start ecosystem.config.js        ← start
//   pm2 restart palf-vision              ← restart after deploy
//   pm2 stop palf-vision                 ← stop
//   pm2 logs palf-vision                 ← view logs
//   pm2 save && pm2 startup              ← persist across reboots

module.exports = {
  apps: [
    {
      name: "palf-vision",

      // next start serves the production build
      script: "node_modules/.bin/next",
      args:   "start",

      // working directory (adjust if you cloned to a different path)
      cwd: "./",

      // environment loaded from .env.local automatically by Next.js;
      // add any process-level overrides here if needed
      env: {
        NODE_ENV: "production",
        PORT:     3000,
      },

      // restart the app if it crashes
      autorestart:  true,
      watch:        false,  // set true only during active dev on the RPi
      max_restarts: 10,
      restart_delay: 3000,  // ms between restart attempts

      // log files (readable via: pm2 logs palf-vision)
      out_file:  "./logs/out.log",
      error_file:"./logs/error.log",
      merge_logs: true,
      log_date_format: "YYYY-MM-DD HH:mm:ss",
    },
  ],
};
