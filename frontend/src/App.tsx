import { Navigate, Route, Routes } from "react-router-dom";
import UploadPage from "./pages/UploadPage";
import SkillGapPage from "./pages/SkillGapPage";
import InterviewPage from "./pages/InterviewPage";
import ReportPage from "./pages/ReportPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<UploadPage />} />
      <Route path="/session/:sessionId/skill-gap" element={<SkillGapPage />} />
      <Route path="/session/:sessionId/interview" element={<InterviewPage />} />
      <Route path="/session/:sessionId/report" element={<ReportPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
