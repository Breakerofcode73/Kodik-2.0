import { Outlet } from 'react-router-dom';
import Header from './Header';
import Footer from './Footer';
import styles from './Layout.module.css'; // если используете CSS Modules

export default function Layout() {
  return (
    <div className={styles.wrapper}>
      <Header />
      <main className={styles.main}>
        <Outlet /> {/* сюда рендерятся дочерние страницы */}
      </main>
      <Footer />
    </div>
  );
}