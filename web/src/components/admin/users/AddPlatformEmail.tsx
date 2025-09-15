import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface Props {
  onSuccess: () => void;
  onFailure: (error: string) => void;
}

const AddPlatformEmail = ({ onSuccess, onFailure }: Props) => {
  const [email, setEmail] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const validateEmail = (email: string) => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!email.trim()) {
      onFailure("Email is required");
      return;
    }

    if (!validateEmail(email)) {
      onFailure("Please enter a valid email address");
      return;
    }

    setIsSubmitting(true);

    try {
      const response = await fetch("/api/manage/platform-emails", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ email: email.trim() }),
      });

      if (response.ok) {
        setEmail("");
        onSuccess();
      } else {
        const error = await response.json();
        onFailure(error.detail || "Failed to add platform email");
      }
    } catch (error) {
      onFailure("Failed to add platform email");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="email">Email Address</Label>
        <Input
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Enter platform email address"
          disabled={isSubmitting}
          required
          className="w-full"
        />
      </div>
      <Button type="submit" disabled={isSubmitting || !email.trim()}>
        {isSubmitting ? "Adding..." : "Add Platform Email"}
      </Button>
    </form>
  );
};

export default AddPlatformEmail; 