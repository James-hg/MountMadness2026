import NavBar from './NavBar';
import FinancialChart from './FinancialChart';

export default function Dashboard() {
  return (
    <>
      <NavBar />
      <div className="container">
        <FinancialChart />
      </div>
    </>
  );
}
