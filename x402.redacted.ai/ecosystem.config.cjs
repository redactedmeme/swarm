module.exports = {
  apps: [
    {
      name: 'express-bun-server',
      script: 'index.js',
      interpreter: 'bun',
      instances: 1,
      exec_mode: 'cluster',
      watch: false,
      max_memory_restart: '500M',
      env: {
        NODE_ENV: 'development',
        PORT: 3000,
        HOST: '0.0.0.0'
      },
      env_production: {
        NODE_ENV: 'production',
        PORT: 3000,
        HOST: '0.0.0.0'
      },
      error_file: './logs/error.log',
      out_file: './logs/out.log',
      log_file: './logs/combined.log',
      time: true,
      merge_logs: true,
      autorestart: true,
      max_restarts: 10,
      min_uptime: '10s',
      listen_timeout: 3000,
      kill_timeout: 5000,
      wait_ready: false,
      // Cron restart - restart every day at 2 AM (optional)
      // cron_restart: '0 2 * * *',
      
      // Advanced process monitoring
      instance_var: 'INSTANCE_ID',
      
      // Log rotation (optional, requires pm2-logrotate module)
      // pm2 install pm2-logrotate
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z'
    }
  ]
};

