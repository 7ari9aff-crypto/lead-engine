import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";

export default function PageNotFound() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-4 bg-background">
      <h1 className="text-6xl font-bold text-foreground">404</h1>
      <p className="text-muted-foreground">الصفحة اللي بتدور عليها مش موجودة</p>
      <Button asChild>
        <Link to="/">الرجوع للرئيسية</Link>
      </Button>
    </div>
  );
}
