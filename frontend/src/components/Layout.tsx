import { NavLink } from "react-router-dom";
import { useAppDispatch, useAppSelector } from "../app/hooks";
import { useLogoutMutation } from "../features/auth/authApi";
import { clearUser } from "../features/auth/authSlice";

interface LayoutProps {
  children: React.ReactNode;
}

const gearClass = ({ isActive }: { isActive: boolean }) =>
  isActive
    ? "inline-flex h-9 w-9 items-center justify-center rounded-md bg-blush text-slate-900"
    : "inline-flex h-9 w-9 items-center justify-center rounded-md text-slate-500 hover:bg-blush/40 hover:text-slate-900";

export function Layout({ children }: LayoutProps) {
  const dispatch = useAppDispatch();
  const user = useAppSelector((state) => state.auth.user);
  const [logout] = useLogoutMutation();

  const handleLogout = async () => {
    await logout();
    dispatch(clearUser());
  };

  return (
    <div className="flex min-h-screen bg-white">
      <aside className="flex w-56 shrink-0 flex-col border-r border-slate-200 bg-white">
        <div className="px-5 py-5">
          <NavLink
            to="/"
            end
            className="block text-lg font-bold text-slate-900 hover:text-blush-dark"
          >
            factful
          </NavLink>
        </div>
        <footer className="mt-auto border-t border-slate-200 px-4 py-4">
          <div className="flex items-center justify-between">
            {user ? (
              <div className="flex min-w-0 items-center gap-3">
                {user.picture && (
                  <img
                    src={user.picture}
                    alt=""
                    className="h-8 w-8 rounded-full"
                  />
                )}
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-slate-900">
                    {user.name}
                  </p>
                  <button
                    onClick={handleLogout}
                    className="text-xs text-slate-400 hover:text-slate-700"
                  >
                    Log out
                  </button>
                </div>
              </div>
            ) : (
              <span />
            )}
            <NavLink to="/settings" aria-label="Settings" className={gearClass}>
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
              </svg>
            </NavLink>
          </div>
        </footer>
      </aside>
      <main className="flex-1 px-6 py-6">{children}</main>
    </div>
  );
}