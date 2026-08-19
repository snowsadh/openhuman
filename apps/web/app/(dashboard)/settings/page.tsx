"use client";

import { useCallback, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import {
  KeyIcon,
  Trash2Icon,
  UserIcon,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  useAuthMe,
  useAuthUpdateMe,
  getAuthMeQueryKey,
  ApiError,
  customInstance,
} from "@repo/api-client";
import { handleSignOut } from "@/hooks/use-auth";
import { useOrgStore } from "@/stores/org";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Spinner } from "@/components/ui/spinner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

interface ProfileFormData {
  name: string;
  email: string;
}

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const clearOrg = useOrgStore((s) => s.clearOrg);
  const profileMutation = useAuthUpdateMe();
  const { data: user, isLoading, isError } = useAuthMe();
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  const isPending = profileMutation.isPending || isDeleting;

  // Password form state
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordErrors, setPasswordErrors] = useState<Record<string, string>>(
    {},
  );
  const [passwordDirty, setPasswordDirty] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isDirty },
  } = useForm<ProfileFormData>({
    defaultValues: { name: "", email: "" },
  });

  useEffect(() => {
    if (user) {
      reset({ name: user.name, email: user.email });
    }
  }, [user, reset]);

  const onProfileSubmit = async (data: ProfileFormData) => {
    try {
      await profileMutation.mutateAsync({
        data: { name: data.name, email: data.email },
      });
      toast.success("Profile updated");
      queryClient.invalidateQueries({ queryKey: getAuthMeQueryKey() });
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error(err.body || "Failed to update profile");
      } else {
        toast.error("Failed to update profile. Please try again.");
      }
    }
  };

  const validatePasswordForm = (): boolean => {
    const errs: Record<string, string> = {};
    if (!currentPassword) errs.currentPassword = "Current password is required";
    if (!newPassword) {
      errs.newPassword = "New password is required";
    } else if (newPassword.length < 6) {
      errs.newPassword = "Must be at least 6 characters";
    }
    if (!confirmPassword) {
      errs.confirmPassword = "Please confirm your new password";
    } else if (newPassword !== confirmPassword) {
      errs.confirmPassword = "Passwords do not match";
    }
    setPasswordErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const onPasswordSubmit = async () => {
    if (!validatePasswordForm()) return;

    try {
      await profileMutation.mutateAsync({
        data: {
          current_password: currentPassword,
          new_password: newPassword,
        },
      });
      toast.success("Password updated");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setPasswordErrors({});
      setPasswordDirty(false);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 400) {
          setPasswordErrors({ currentPassword: err.body });
        } else {
          toast.error(err.body || "Failed to update password");
        }
      } else {
        toast.error("Failed to update password. Please try again.");
      }
    }
  };

  const handleDeleteAccount = useCallback(async () => {
    setIsDeleting(true);
    try {
      await customInstance({ url: "/api/auth/me", method: "DELETE" });
      clearOrg();
      toast.success("Account deleted");
      handleSignOut("/sign-up");
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error(err.body || "Failed to delete account");
      } else {
        toast.error("Failed to delete account. Please try again.");
      }
    } finally {
      setIsDeleting(false);
      setDeleteDialogOpen(false);
    }
  }, [clearOrg]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Spinner />
      </div>
    );
  }

  if (isError || !user) {
    return (
      <div className="flex flex-col items-center justify-center py-24">
        <UserIcon className="size-10 text-muted-foreground/40" />
        <p className="mt-3 text-sm text-muted-foreground">
          Failed to load user profile.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 px-6 py-6">
      <div className="flex items-center gap-2.5">
        <UserIcon className="size-5 text-muted-foreground" />
        <h1 className="text-lg font-semibold tracking-tight text-foreground">
          Settings
        </h1>
      </div>

      {/* Profile */}
      <form
        onSubmit={handleSubmit(onProfileSubmit)}
        className="mx-auto w-full max-w-2xl"
      >
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2.5">
              <UserIcon className="size-4 text-muted-foreground" />
              <CardTitle>Profile</CardTitle>
            </div>
            <CardDescription>
              Your name and email address are used across the workspace.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                disabled={isPending}
                {...register("name", {
                  required: "Name is required",
                  minLength: {
                    value: 1,
                    message: "Name must be at least 1 character",
                  },
                })}
              />
              {errors.name && (
                <p className="text-sm text-destructive">
                  {errors.name.message}
                </p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                disabled={isPending}
                {...register("email", {
                  required: "Email is required",
                  pattern: {
                    value: /^\S+@\S+$/i,
                    message: "Invalid email address",
                  },
                })}
              />
              {errors.email && (
                <p className="text-sm text-destructive">
                  {errors.email.message}
                </p>
              )}
            </div>
          </CardContent>
          <CardFooter className="justify-between">
            <p className="text-xs text-muted-foreground">
              Member since{" "}
              {new Date(user.created_at).toLocaleDateString("en-US", {
                year: "numeric",
                month: "long",
                day: "numeric",
              })}
            </p>
            <Button
              type="submit"
              size="sm"
              disabled={!isDirty || isPending}
            >
              {profileMutation.isPending ? "Saving..." : "Save changes"}
            </Button>
          </CardFooter>
        </Card>
      </form>

      {/* Password */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onPasswordSubmit();
        }}
        className="mx-auto w-full max-w-2xl"
      >
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2.5">
              <KeyIcon className="size-4 text-muted-foreground" />
              <CardTitle>Password</CardTitle>
            </div>
            <CardDescription>
              Update your password. You&apos;ll need to enter your current
              password to make changes.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="currentPassword">Current password</Label>
              <Input
                id="currentPassword"
                type="password"
                disabled={isPending}
                value={currentPassword}
                onChange={(e) => {
                  setCurrentPassword(e.target.value);
                  setPasswordDirty(true);
                  if (passwordErrors.currentPassword) {
                    setPasswordErrors((p) => ({ ...p, currentPassword: "" }));
                  }
                }}
              />
              {passwordErrors.currentPassword && (
                <p className="text-sm text-destructive">
                  {passwordErrors.currentPassword}
                </p>
              )}
            </div>
            <Separator />
            <div className="space-y-1.5">
              <Label htmlFor="newPassword">New password</Label>
              <Input
                id="newPassword"
                type="password"
                disabled={isPending}
                value={newPassword}
                onChange={(e) => {
                  setNewPassword(e.target.value);
                  setPasswordDirty(true);
                  if (passwordErrors.newPassword) {
                    setPasswordErrors((p) => ({ ...p, newPassword: "" }));
                  }
                }}
              />
              {passwordErrors.newPassword && (
                <p className="text-sm text-destructive">
                  {passwordErrors.newPassword}
                </p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="confirmPassword">Confirm new password</Label>
              <Input
                id="confirmPassword"
                type="password"
                disabled={isPending}
                value={confirmPassword}
                onChange={(e) => {
                  setConfirmPassword(e.target.value);
                  setPasswordDirty(true);
                  if (passwordErrors.confirmPassword) {
                    setPasswordErrors((p) => ({
                      ...p,
                      confirmPassword: "",
                    }));
                  }
                }}
              />
              {passwordErrors.confirmPassword && (
                <p className="text-sm text-destructive">
                  {passwordErrors.confirmPassword}
                </p>
              )}
            </div>
          </CardContent>
          <CardFooter className="justify-end">
            <Button
              type="submit"
              size="sm"
              disabled={!passwordDirty || isPending}
            >
              {profileMutation.isPending ? "Updating..." : "Update password"}
            </Button>
          </CardFooter>
        </Card>
      </form>

      <Separator className="mx-auto max-w-2xl" />

      {/* Danger Zone */}
      <div className="mx-auto w-full max-w-2xl space-y-4">
        <div className="flex items-center gap-2">
          <Trash2Icon className="size-4 text-destructive" />
          <h2 className="text-sm font-semibold text-destructive">
            Danger Zone
          </h2>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Delete account</CardTitle>
            <CardDescription>
              Permanently delete your account and all associated data. Your
              organizations will also be removed. This action cannot be undone.
            </CardDescription>
          </CardHeader>
          <CardFooter>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => setDeleteDialogOpen(true)}
              disabled={isDeleting}
            >
              {isDeleting ? "Deleting..." : "Delete account"}
            </Button>
          </CardFooter>
        </Card>
      </div>

      <AlertDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete account?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete{" "}
              <span className="font-medium text-foreground">
                {user.name}
              </span>
              &apos;s account and all associated data, including organizations.
              This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={handleDeleteAccount}
              disabled={isDeleting}
            >
              {isDeleting ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
