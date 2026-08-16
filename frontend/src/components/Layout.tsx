import { NavLink } from "react-router-dom";
import { useAppDispatch, useAppSelector } from "../app/hooks";
import { useLogoutMutation } from "../features/auth/authApi";
import { clearUser } from "../features/auth/authSlice";

interface LayoutProps {
  children: React.ReactNode;
}

const navClass = ({ isActive }: { isActive: boolean }) =>
  isActive ? "text-slate-900 font-medium" : "text-slate-500 hover:text-slate-900";

export function Layout({ children }: LayoutProps) {
  const dispatch = useAppDispatch();
  const user = useAppSelector((state) => state.auth.user);
  const [logout] = useLogoutMutation();

  const handleLogout = async () => {
    await logout();
    dispatch(clearUser());
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-6">
            <span className="text-lg font-bold text-slate-900">factful</span>
            <nav className="flex gap-4 text-sm">
              <NavLink to="/" end className={navClass}>
                Stories
              </NavLink>
              <NavLink to="/settings" className={navClass}>
                Settings
              </NavLink>
            </nav>
          </div>
          {user && (
            <div className="flex items-center gap-3 text-sm text-slate-600">
              {user.picture && (
                <img
                  src={user.picture}
                  alt=""
                  className="h-8 w-8 rounded-full"
                />
              )}
              <span>{user.name}</span>
              <button
                onClick={handleLogout}
                className="text-slate-400 hover:text-slate-700"
              >
                Log out
              </button>
            </div>
          )}
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>
    </div>
  );
}
