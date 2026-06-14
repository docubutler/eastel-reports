/*
Query 4: Total MOUs for Voice MO On Net calls according to config date

Output:
{
  "Service Type": "Voice",
  "Charge Type": "MO",
  "Call Type": "On Net",
  "MOUs": 1234.56
}

*/


const reportStart = new Date(config.variables.start_date);
const reportEnd = new Date(config.variables.end_date);
reportEnd.setDate(reportEnd.getDate() + 1);

db.usage_logs.aggregate([
  {
    $match: {
      rat_type: "VO",
      service_type_sub_cd: "MO",
      rating_group: { $in: ["ONNET"] },
      usage_start_time: {
        $gte: ISODate(reportStart),
        $lt: ISODate(reportEnd)
      }
    }
  },
  {
    $group: {
      _id: "$rating_group",
      MOUs: {
        $sum: {
          $divide: [{ $toDouble: "$usage_unit" }, 60]
        }
      }
    }
  },
  {
    $project: {
      _id: 0,
      "Service Type": "Voice",
      "Charge Type": "MO",
      "Call Type": {
        $switch: {
          branches: [
            { case: { $eq: ["$_id", "ONNET"] }, then: "On Net" }
          ]
        }
      },
      MOUs: { $round: ["$MOUs", 2] },
      sort_order: {
        $cond: [
          { $eq: ["$_id", "ONNET"] },
          1,
          2
        ]
      }
    }
  },
  {
    $sort: {
      sort_order: 1
    }
  },
  {
    $project: {
      sort_order: 0
    }
  }
]);