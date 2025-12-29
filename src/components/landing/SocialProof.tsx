const testimonials = [
  {
    quote: "I used to spend 45 minutes at end of day doing CRM. Now it takes 5 minutes.",
    author: "Carlos M.",
    role: "Account Executive",
    company: "SaaS Company (150 employees)",
    initials: "CM",
  },
  {
    quote: "My team's CRM compliance went from 60% to 95% in two weeks.",
    author: "Ana R.",
    role: "Head of Sales",
    company: "Tech Startup",
    initials: "AR",
  },
  {
    quote: "I log deals while walking between meetings. My manager thinks I'm a CRM machine.",
    author: "David L.",
    role: "Field Sales Rep",
    company: "",
    initials: "DL",
  },
  {
    quote: "Finally, a tool that actually saves time instead of creating more work.",
    author: "Maria S.",
    role: "Sales Manager",
    company: "",
    initials: "MS",
  },
];

const SocialProof = () => {
  return (
    <section className="py-20 bg-secondary/50 grain-overlay">
      <div className="container mx-auto px-6 relative z-10">
        <h2 className="text-3xl md:text-4xl font-bold text-foreground text-center mb-12">
          Sales Teams Love Voicfy
        </h2>

        <div className="grid md:grid-cols-2 gap-6 max-w-4xl mx-auto">
          {testimonials.map((testimonial, index) => (
            <div
              key={index}
              className="bg-card rounded-2xl p-6 shadow-soft border border-border"
            >
              <blockquote className="text-foreground mb-4 leading-relaxed">
                "{testimonial.quote}"
              </blockquote>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-beige/20 flex items-center justify-center">
                  <span className="text-sm font-semibold text-beige">{testimonial.initials}</span>
                </div>
                <div>
                  <p className="font-medium text-foreground text-sm">{testimonial.author}</p>
                  <p className="text-xs text-muted-foreground">
                    {testimonial.role}{testimonial.company && `, ${testimonial.company}`}
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default SocialProof;
