import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { AuthGate } from "./features/auth/AuthGate";
import { StoryEditor } from "./features/editor/StoryEditor";
import { Gallery } from "./features/gallery/Gallery";
import { Settings } from "./pages/Settings";

export default function App() {
  return (
    <AuthGate>
      <Layout>
        <Routes>
          <Route path="/" element={<Gallery />} />
          <Route path="/stories/:storyId" element={<StoryEditor />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </Layout>
    </AuthGate>
  );
}
