import NavBar from './NavBar';
import FinancialChart from './FinancialChart';
import ChatPanel from './ChatPanel';

export default function Dashboard() {
  return (
    <>
      <NavBar />
      <div className="container">
        <FinancialChart />
        <ChatPanel />
      </div>
    </>
  );
}
