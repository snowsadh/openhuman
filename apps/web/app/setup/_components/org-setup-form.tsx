"use client";

import { useForm } from "react-hook-form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";

export interface OrgSetupFormData {
  name: string;
  description: string;
  what_it_does: string;
  website_url: string;
}

interface Props {
  onSubmit: (data: OrgSetupFormData) => void;
  isSubmitting: boolean;
  error: string | null;
}

export function OrgSetupForm({ onSubmit, isSubmitting, error }: Props) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<OrgSetupFormData>();

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
      <div className="space-y-1.5">
        <Label htmlFor="name">
          Organization name <span className="text-destructive">*</span>
        </Label>
        <Input
          id="name"
          placeholder="Acme Corp"
          disabled={isSubmitting}
          {...register("name", {
            required: "Organization name is required",
            minLength: {
              value: 2,
              message: "Name must be at least 2 characters",
            },
          })}
        />
        {errors.name && (
          <p className="text-sm text-destructive">{errors.name.message}</p>
        )}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="description">Description</Label>
        <Textarea
          id="description"
          placeholder="A brief description of your organization..."
          rows={3}
          disabled={isSubmitting}
          {...register("description")}
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="what_it_does">
          What does your company do?
        </Label>
        <Textarea
          id="what_it_does"
          placeholder="e.g. We build AI-powered analytics tools for healthcare..."
          rows={3}
          disabled={isSubmitting}
          {...register("what_it_does")}
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="website_url">
          Company website
        </Label>
        <Input
          id="website_url"
          type="url"
          placeholder="https://acme.com"
          disabled={isSubmitting}
          {...register("website_url")}
        />
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Button type="submit" className="w-full" disabled={isSubmitting}>
        {isSubmitting && <Spinner className="mr-2" />}
        {isSubmitting ? "Saving…" : "Continue"}
      </Button>
    </form>
  );
}
