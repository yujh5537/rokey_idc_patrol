import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Vite 개발 서버 설정이다.
// 브라우저는 5173 포트의 React 화면에 접속하지만,
// /api 로 시작하는 요청은 아래 proxy 설정을 통해 FastAPI(8000)로 전달된다.
// 예: http://localhost:5173/api/v1/robots
//   -> http://127.0.0.1:8000/api/v1/robots
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        // /api/v1/ws WebSocket 연결도 같은 FastAPI 서버로 전달한다.
        ws: true,
      },
    },
  },
});
