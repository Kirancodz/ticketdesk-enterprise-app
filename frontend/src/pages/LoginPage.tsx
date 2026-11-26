import React, { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Lock,
  Mail,
  Shield,
  X,
} from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import { ApiError, apiRequest } from "../services/api";

const loginSchema = z.object({
  email: z.string().email("Please enter a valid corporate email address"),
  password: z.string().min(4, "Password is required"),
});

type LoginFormValues = z.infer<typeof loginSchema>;

export const LoginPage: React.FC = () => {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const passwordChanged =
    (location.state as { passwordChanged?: boolean } | null)?.passwordChanged === true;
  const [serverError, setServerError] = useState<string | null>(null);
  const [resetSuccessBanner, setResetSuccessBanner] = useState<string | null>(null);

  // Admin-assisted password recovery
  const [forgotOpen, setForgotOpen] = useState(false);
  const [fpEmail, setFpEmail] = useState("");
  const [fpEmployeeId, setFpEmployeeId] = useState("");
  const [fpReason, setFpReason] = useState("");
  const [fpError, setFpError] = useState<string | null>(null);
  const [fpLoading, setFpLoading] = useState(false);

  const returnPath = (location.state as { from?: { pathname?: unknown } } | null)?.from?.pathname;
  const from =
    typeof returnPath === "string" &&
    returnPath.startsWith("/") &&
    !returnPath.startsWith("//") &&
    !/[\\?#\u0000-\u0020\u007f]/.test(returnPath)
      ? returnPath
      : "/dashboard";

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      email: "",
      password: "",
    },
  });

  const onSubmit = async (values: LoginFormValues) => {
    setServerError(null);
    setResetSuccessBanner(null);
    try {
      const authenticatedUser = await login(values.email, values.password);

      if (authenticatedUser.must_change_password) {
        navigate("/change-password", { replace: true });
        return;
      }

      navigate({ pathname: from }, { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setServerError(err.message);
      } else {
        setServerError("Unable to reach authentication server. Please verify backend status.");
      }
    }
  };

  const openForgotModal = () => {
    setResetSuccessBanner(null);
    setFpEmail("");
    setFpEmployeeId("");
    setFpReason("");
    setFpError(null);
    setForgotOpen(true);
  };

  const handleRequestRecoveryTicket = async (
    event: React.FormEvent<HTMLFormElement>
  ) => {
    event.preventDefault();
    setFpError(null);

    const email = fpEmail.trim();
    const employeeId = fpEmployeeId.trim();
    const reason = fpReason.trim();

    if (
      email.length > 254 ||
      !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
    ) {
      setFpError("Enter a valid corporate email address.");
      return;
    }

    if (!employeeId || employeeId.length > 50) {
      setFpError("Enter a valid Employee / Consultant ID.");
      return;
    }

    if (reason.length < 10 || reason.length > 500) {
      setFpError("Reset reason must contain 10 to 500 characters.");
      return;
    }

    setFpLoading(true);

    try {
      await apiRequest<{ message: string }>(
        "/auth/forgot-password/request-ticket",
        {
          method: "POST",
          body: JSON.stringify({ email, employee_id: employeeId, reason }),
        }
      );

      setForgotOpen(false);
      setFpEmail("");
      setFpEmployeeId("");
      setFpReason("");
      setResetSuccessBanner(
        "Request submitted successfully!"
      );
    } catch (err) {
      setFpError(
        err instanceof ApiError && err.status === 400
          ? "Incorrect Email ID or Employee ID."
          : err instanceof ApiError && err.status === 429
            ? "Too many requests. Please try again later."
            : "Unable to submit the request. Please try again later or contact IT support."
      );
    } finally {
      setFpLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-white text-slate-900 px-4 py-8 sm:px-6 sm:py-12">
      <header className="mx-auto mb-8 flex w-full max-w-xl flex-col items-center text-center sm:mb-10">
        <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600 shadow-lg shadow-blue-600/20">
          <Shield className="h-5 w-5 text-white" />
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
          TicketDesk Enterprise
        </h1>
        <p className="mt-2 text-xs font-medium text-blue-600 sm:text-sm">
          Enterprise IT Service Management Platform
        </p>
      </header>

      <main className="mx-auto w-full max-w-md">
        <div>
          <div>
            <h2 className="text-2xl font-bold tracking-tight text-slate-900">
              Sign in to your workspace
            </h2>
            <p className="mt-1.5 text-sm text-slate-500">
              Enter your corporate credentials to sign in.
            </p>
          </div>

          {(resetSuccessBanner || passwordChanged) && (
            <div className="mt-5 p-3.5 rounded-lg bg-emerald-50 border border-emerald-200 flex items-start gap-2.5 text-xs text-emerald-800">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
              <span>
                  {passwordChanged
                    ? "Password changed successfully. Please sign in with your new password."
                    : resetSuccessBanner}
                </span>
            </div>
          )}

          {serverError && (
            <div className="mt-5 p-3.5 rounded-lg bg-red-50 border border-red-200 flex items-start gap-2.5 text-xs text-red-700">
              <AlertCircle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
              <span>{serverError}</span>
            </div>
          )}

          <form onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-4" noValidate>
            <div>
              <label
                htmlFor="email"
                className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1.5"
              >
                Corporate Email
              </label>
              <div className="relative">
                <Mail className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
                <input
                  id="email"
                  type="email"
                  autoComplete="email"
                  placeholder="name@ticketdesk.enterprise"
                  {...register("email")}
                  className="w-full pl-10 pr-4 py-2.5 text-sm bg-slate-50 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600 focus:bg-white transition-all"
                />
              </div>
              {errors.email && (
                <p className="mt-1 text-xs text-red-600">{errors.email.message}</p>
              )}
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label
                  htmlFor="password"
                  className="block text-xs font-semibold uppercase tracking-wider text-slate-700"
                >
                  Password
                </label>
                <button
                  type="button"
                  onClick={openForgotModal}
                  className="text-xs font-semibold text-blue-600 hover:text-blue-700 hover:underline cursor-pointer"
                >
                  Forgot password?
                </button>
              </div>
              <div className="relative">
                <Lock className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
                <input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  placeholder="••••••••••••"
                  {...register("password")}
                  className="w-full pl-10 pr-4 py-2.5 text-sm bg-slate-50 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600 focus:bg-white transition-all"
                />
              </div>
              {errors.password && (
                <p className="mt-1 text-xs text-red-600">{errors.password.message}</p>
              )}
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full py-2.5 px-4 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white font-semibold text-sm shadow-xs flex items-center justify-center gap-2 transition-colors cursor-pointer"
            >
              <span>{isSubmitting ? "Authenticating..." : "Sign In to TicketDesk"}</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </form>


        </div>
      </main>

      {/* Admin-assisted password recovery request */}
      {forgotOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/70 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="recovery-title"
        >
          <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 id="recovery-title" className="text-lg font-bold text-slate-900">
                  Request Password Recovery
                </h3>
                <p className="mt-2 text-sm text-slate-600">
                  Enter your corporate email or Employee ID.
                  The Identity &amp; Access team will review your request.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setForgotOpen(false)}
                disabled={fpLoading}
                aria-label="Close"
                className="text-slate-400 hover:text-slate-700 disabled:opacity-50"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <p className="mt-4 rounded-lg bg-blue-50 p-3 text-xs text-blue-800">
              An administrator must independently verify your identity before
              resetting your password. Do not share passwords or OTPs in tickets.
            </p>

            {fpError && (
              <div className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">
                <AlertCircle className="mr-2 inline h-4 w-4" />
                {fpError}
              </div>
            )}

            <form onSubmit={handleRequestRecoveryTicket} className="mt-5 space-y-4">
              <div>
                <label
                  htmlFor="recovery-identifier"
                  className="mb-1 block text-sm font-semibold text-slate-700"
                >
                  Corporate Email ID
                </label>
                <input
                  id="recovery-email"
                  type="email"
                  autoComplete="email"
                  value={fpEmail}
                  onChange={(event) => setFpEmail(event.target.value)}
                  maxLength={254}
                  required
                  placeholder="Enter your corporate email"
                  className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm focus:border-blue-600 focus:outline-none"
                />
              </div>

              <div>
                <label
                  htmlFor="recovery-employee-id"
                  className="mb-1 block text-sm font-semibold text-slate-700"
                >
                  Employee / Consultant ID
                </label>
                <input
                  id="recovery-employee-id"
                  type="text"
                  value={fpEmployeeId}
                  onChange={(event) => setFpEmployeeId(event.target.value)}
                  maxLength={50}
                  required
                  placeholder="Enter your ID"
                  className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm focus:border-blue-600 focus:outline-none"
                />
              </div>

              <div>
                <label
                  htmlFor="recovery-reason"
                  className="mb-1 block text-sm font-semibold text-slate-700"
                >
                  Reason for Password Reset
                </label>
                <textarea
                  id="recovery-reason"
                  rows={3}
                  value={fpReason}
                  onChange={(event) => setFpReason(event.target.value)}
                  minLength={10}
                  maxLength={500}
                  required
                  placeholder="Example: I forgot my password and cannot log in."
                  className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm focus:border-blue-600 focus:outline-none"
                />
                <p className="mt-1 text-xs text-slate-500">
                  Do not enter passwords, OTPs, or security answers.
                </p>
              </div>

              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  disabled={fpLoading}
                  onClick={() => setForgotOpen(false)}
                  className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={fpLoading}
                  className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  {fpLoading ? "Submitting..." : "Submit Recovery Request"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
