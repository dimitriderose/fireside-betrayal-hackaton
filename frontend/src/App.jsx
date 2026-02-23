import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { GameProvider } from './context/GameContext.jsx'
import Landing from './components/Landing/Landing.jsx'
import JoinLobby from './components/JoinLobby/JoinLobby.jsx'
import GameScreen from './components/Game/GameScreen.jsx'
import GameOver from './components/GameOver/GameOver.jsx'
import TutorialPage from './components/Tutorial/TutorialPage.jsx'

export default function App() {
  return (
    <GameProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/tutorial" element={<TutorialPage />} />
          <Route path="/join" element={<JoinLobby />} />
          <Route path="/join/:gameCode" element={<JoinLobby />} />
          <Route path="/game/:gameId" element={<GameScreen />} />
          <Route path="/gameover/:gameId" element={<GameOver />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </GameProvider>
  )
}
