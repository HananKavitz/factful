import { useEffect, useState } from "react";
import { useAppDispatch, useAppSelector } from "../../app/hooks";
import { useGetMeQuery, useMockLoginMutation } from "./authApi";
import { setUser } from "./authSlice";

interface AuthGateProps {
  children: React.ReactNode;
}

export function AuthGate({ children }: AuthGateProps) {
  const dispatch = useAppDispatch();
  const user = useAppSelector((state) => state.auth.user);
  const { data, isUninitialized, isFetching, isSuccess, isError } = useGetMeQuery();
  const [mockLogin, { isLoading: loggingIn }] = useMockLoginMutation();
  const [email, setEmail] = useState("");

  useEffect(() => {
    if (isSuccess && data) dispatch(setUser(data));
    if (isError) dispatch(setUser(null));
  }, [isSuccess, isError, data, dispatch]);

  const handleMockLogin = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!email.trim()) return;
    const loggedIn = await mockLogin({ email: email.trim() }).unwrap();
    dispatch(setUser(loggedIn));
  };

  if (user) {
    return <>{children}</>;
  }

  if (isUninitialized || isFetching) {
    return (
      <div className="flex h-screen items-center justify-center text-slate-400">
        Loading…
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
        <div className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-8 shadow-sm">
          <h1 className="text-2xl font-bold text-slate-900">factful</h1>
          <p className="mt-2 text-sm text-slate-500">
            Sign in to manage your fact-checked stories.
          </p>
          <a
            href="/api/auth/login"
            className="mt-6 flex w-full items-center justify-center rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Sign in with Google
          </a>
          {import.meta.env.DEV && (
            <form onSubmit={handleMockLogin} className="mt-4 space-y-2 border-t border-slate-100 pt-4">
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@example.com"
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
              <button
                type="submit"
                disabled={loggingIn || !email.trim()}
                className="w-full rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
              >
                Dev mock login
              </button>
            </form>
          )}
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
