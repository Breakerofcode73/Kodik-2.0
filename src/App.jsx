import { Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout/Layout';
import HomePage from './pages/HomePage';
import SearchResultsPage from './pages/SearchResultsPage';
import InfoPage from './pages/InfoPage';
import DownloadPage from './pages/DownloadPage';
import WatchPage from './pages/WatchPage';
import RoomPage from './pages/RoomPage';
import LegacyRedirect from './pages/LegacyRedirect';

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        {/* Главная страница с поиском */}
        <Route path="/" element={<HomePage />} />

        {/* Результаты поиска */}
        <Route path="/search/kdk/:query" element={<SearchResultsPage />} />

        {/* Информация о тайтле */}
        <Route path="/download/:serv/:id" element={<InfoPage />} />

        {/* Выбор серии и качества */}
        <Route path="/download/:serv/:id/:data" element={<DownloadPage />} />

        {/* Просмотр видео */}
        <Route
          path="/watch/:serv/:id/:data/:seria/:quality?/:timing?"
          element={<WatchPage />}
        />

        {/* Комната совместного просмотра */}
        <Route path="/room/:roomId" element={<RoomPage />} />

        {/* Обратная совместимость: старые ссылки типа /download/.../watch-1 */}
        <Route
          path="/download/:serv/:id/:data/watch-:seria"
          element={<LegacyRedirect />}
        />

        {/* Редирект с несуществующих маршрутов на главную (опционально) */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}